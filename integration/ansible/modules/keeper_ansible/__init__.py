#  _  __
# | |/ /___ ___ _ __  ___ _ _ ®
# | ' </ -_) -_) '_ \/ -_) '_|
# |_|\_\___\___| .__/\___|_|
#              |_|
#
# Keeper Commander
# Copyright 2021 Keeper Security Inc.
# Contact: ops@keepersecurity.com
#

from keepercommandersm import Commander
from keepercommandersm.storage import FileKeyValueStorage, InMemoryKeyValueStorage
from ansible.utils.display import Display
from ansible.errors import AnsibleError
import os
import json
from re import sub
from enum import Enum


display = Display()


class KeeperFieldType(Enum):
    FIELD = "field"
    CUSTOM_FIELD = "custom_field"
    FILE = "file"

    @staticmethod
    def get_enum(value):
        for e in KeeperFieldType:
            if e.value == value:
                return e
        return None


class KeeperAnsible:

    """ A class containing common method used by the Ansible plugin and also talked to Keeper Python SDK
    """

    KEY_PREFIX = "keeper"
    KEY_CONFIG_FILE_SUFFIX = "config_file"
    ALLOWED_FIELDS = ["field", "custom_field", "file"]
    CLIENT_KEY_ENV = "KEEPER_SECRET_KEY"
    CONFIG_CLIENT_KEY = "clientKey"
    FORCE_CONFIG_FILE = "force_config_write"
    KEY_SSL_VERIFY = "verify_ssl_certs"

    @staticmethod
    def get_client(**kwargs):
        return Commander(**kwargs)

    def __init__(self, task_vars):

        """ Build the config used by the Keeper Python SDK

        The configuration is mainly read from a JSON file.
        """

        def camel_case(text):
            text = sub(r"([_\-])+", " ", text).title().replace(" ", "")
            return text[0].lower() + text[1:]

        try:

            keeper_config_file_key = KeeperAnsible.keeper_key(KeeperAnsible.KEY_CONFIG_FILE_SUFFIX)
            keeper_verify_ssl_certs = KeeperAnsible.keeper_key(KeeperAnsible.KEY_SSL_VERIFY)

            # By default we want to check SSL certs, allow to be controlled via vars and also environmental vars
            verify_ssl_certs = task_vars.get(keeper_verify_ssl_certs, os.environ.get("PYTHONHTTPSVERIFY", True))

            # If the config location is defined, or a file exists at the default location.
            config_file = task_vars.get(keeper_config_file_key)
            if config_file is None:
                config_file = FileKeyValueStorage.default_config_file_location

            if os.path.isfile(config_file) is True:
                display.debug("Loading keeper config file file {}.".format(config_file))
                self.client = KeeperAnsible.get_client(
                    config=FileKeyValueStorage(config_file_location=config_file)
                )

            # Else config values in the Ansible variable.
            else:
                display.debug("Loading keeper config from Ansible vars.")

                config_dict = {}
                # Convert Ansible variables into the keys used by Commander's config.
                for key in ["url", "client_id", "client_key", "app_key", "private_key", "bat", "binding_key", "server"]:
                    keeper_key = KeeperAnsible.keeper_key(key)
                    camel_key = camel_case(key)
                    if keeper_key in task_vars:
                        config_dict[camel_key] = task_vars[keeper_key]

                # If the secret client key is in the environment, override the Ansible var.
                if os.environ.get(KeeperAnsible.CLIENT_KEY_ENV) is not None:
                    config_dict[KeeperAnsible.CONFIG_CLIENT_KEY] = os.environ.get(KeeperAnsible.CLIENT_KEY_ENV)

                # If no variables were passed in throw an error.
                if len(config_dict) == 0:
                    raise AnsibleError("There is no config file and the Ansible variable contain no config keys. Will"
                                       " not be able to connect to the Keeper server.")

                # Since we are getting our variables from Ansible, we want to default using the in memory storage so
                # not to leave config files laying around.
                in_memory_storage = True

                # Does the user want to write the config to a file? Then don't use the in memory storage.
                if bool(task_vars.get(KeeperAnsible.keeper_key(KeeperAnsible.FORCE_CONFIG_FILE), False)) is True:
                    in_memory_storage = False
                # If the is only 1 key, we want to force the config to write to the file.
                elif len(config_dict) == 1 and KeeperAnsible.CONFIG_CLIENT_KEY in config_dict:
                    in_memory_storage = False

                if in_memory_storage is True:
                    config_instance = InMemoryKeyValueStorage(config=config_dict)
                else:
                    # Write the variables we have to a JSON file.
                    with open(config_file, "w") as fh:
                        json.dump(config_dict, fh, indent=4)
                        fh.close()

                    config_instance = FileKeyValueStorage(config_file_location=config_file)
                    config_instance.read_storage()

                self.client = KeeperAnsible.get_client(
                    config=config_instance,
                    verify_ssl_certs=verify_ssl_certs
                )

        except Exception as err:
            raise Exception("Keeper Ansible error: {}".format(err))

    @staticmethod
    def keeper_key(key):
        return "{}_{}".format(KeeperAnsible.KEY_PREFIX, key)

    def get_record(self, uid):

        try:
            records = self.client.get_secrets([uid])
            if records is None or len(records) == 0:
                raise ValueError("The uid {} was not found in the Keeper Vault.".format(uid))
        except Exception as err:
            raise Exception("Cannot get record: {}".format(err))

        return records[0]

    def get_value(self, uid, field_type, key, allow_array=False):

        record = self.get_record(uid)

        values = None
        if field_type == KeeperFieldType.FIELD:
            values = record.field(key)
        elif field_type == KeeperFieldType.CUSTOM_FIELD:
            values = record.custom_field(key)
        elif field_type == KeeperFieldType.FILE:
            file = record.find_file_by_title(key)
            if file is not None:
                values = [file.get_file_data()]
        else:
            raise AnsibleError("Cannot get_value. The field type ENUM of {} is invalid.".format(field_type))

        if values is None:
            raise AnsibleError("Cannot find key {} in the record for uid {} and field_type {}".format(key, uid,
                                                                                                      field_type.name))

        if len(values) == 0:
            display.debug("The value for uid {}, field_type {}, key {} was None or was an empty list.".format(
                uid, field_type.name, key))
            return None

        # If we want the entire array, then just return what we got from the field.
        if allow_array is True:
            return values

        # Else return the first item.
        return values[0]

    def set_value(self, uid, field_type, key, value):

        record = self.get_record(uid)

        if field_type == KeeperFieldType.FIELD:
            record.field(key, value)
        elif field_type == KeeperFieldType.CUSTOM_FIELD:
            record.custom_field(key, value)
        elif field_type == KeeperFieldType.FILE:
            raise AnsibleError("Cannot save a file from the ansible playbook/role to Keeper.")
        else:
            raise AnsibleError("Cannot set_value. The field type ENUM of {} is invalid.".format(field_type))

        self.client.save(record)

    @staticmethod
    def get_field_type_enum_and_key(args):

        """Get the field type enum and field key in the Ansible args for a task.

        For a task that, only allowed one of the allowed field, this method will find the type of field and
        the key/label for that field.

        If multiple fields types are specified, an error will be thrown. If no fields are found, an error will be
        thrown.

        The method will return the KeeperFieldType enum for the field type and the name of the field in Keeper that
        the task requires.
        """

        field_type = []
        field_key = None
        for key in KeeperAnsible.ALLOWED_FIELDS:
            if args.get(key) is not None:
                field_type.append(key)
                field_key = args.get(key)

        if len(field_type) == 0:
            raise AnsibleError("Either field, custom_field or file needs to set to a non-blank value for keeper_copy.")
        if len(field_type) > 1:
            raise AnsibleError("Found multiple field types. Only one of the following key can be set: field, "
                               "custom_field or file.")

        return KeeperFieldType.get_enum(field_type[0]), field_key
