import unittest
from unittest.mock import patch
from keepercommandersm import Commander
from keepercommandersm import mock
from keepercommandersm.storage import InMemoryKeyValueStorage
import os
import sys
from .ansible_test_framework import AnsibleTestFramework
import tempfile


class KeeperGetSdkTest(unittest.TestCase):

    """Integration test with the SDK

    This test uses the keepercommandersm.mock functions.

    """

    def setUp(self):

        # Add in addition Python libs. This includes the base
        # module for Keeper Ansible and the Keeper SDK.
        self.base_dir = os.path.dirname(os.path.realpath(__file__))
        sys.path.append(os.path.join(self.base_dir, "..", "modules"))
        sys.path.append(os.path.join(self.base_dir, "..", "..", "..", "..", "sdk", "python", "core"))

        self.ansible_base_dir = os.path.join(self.base_dir, "ansible_example")

    def test_keeper_update_mock(self):

        fake_config = InMemoryKeyValueStorage(
            config={
                "appKey": "9vVajcvJTGsa2Opc_jvhEiJLRKHtg2Rm4PAtUoP3URw",
                "clientId": "rYebZN1TWiJagL-wHxYboe1vPje10zx1JCJR2bpGILlhIRg7HO26C7HnW-NNHDaq_8SQQ2sOYYT1Nhk5Ya_SkQ",
                "clientKey": "zKoSCC6eNrd3N9CByRBsdChSsTeDEAMvNj9Bdh7BJuo",
                "privateKey": "MIGHAgEAMBMGByqGSM49AgEGCCqGSM49AwEHBG0wawIBAQQgaKWvicgtslVJKJU-_LBMQQGfJAycwOtx9djH0YE"
                              "vBT-hRANCAASB1L44QodSzRaIOhF7f_2GlM8Fg0R3i3heIhMEdkhcZRDLxIGEeOVi3otS0UBFTrbET6joq0xCjh"
                              "KMhHQFaHYI"
            }
        )

        # Get an instance of Commander and use our fake config
        commander = Commander(config=fake_config)

        with patch("keeper_ansible.KeeperAnsible.get_client") as mock_client:
            mock_client.return_value = commander

            # Pass in our Commander into the queue so it gets patched.
            queue = mock.ResponseQueue(client=commander)

            # Create our response for the Commander mock
            get_res = mock.Response()
            record = get_res.add_record(title="My Record 1", uid="TRd_567FkHy-CeGsAzs8aA")
            record.field("login", "My Login 1")
            record.field("password", "password_ddd")
            record.custom_field("My Custom 1", "custom1")

            # Make a record for the updated.
            set_res = mock.Response()
            record = set_res.add_record(title="My Record 1", uid="TRd_567FkHy-CeGsAzs8aA")
            record.field("login", "My Login 1")
            record.field("password", "NEW PASSWORD")
            record.custom_field("My Custom 1", "custom1")

            # This is for keeper_get
            queue.add_response(get_res)

            # Save
            queue.add_response(mock.Response(content="", status_code=200))

            # This is for keeper_set and the save response
            queue.add_response(set_res)

            # Restore Save
            queue.add_response(mock.Response(content="", status_code=200))

            # We are unittest mock patching our ansible module. We are replacing the
            # method that gets an instance of Commander with a mock method that
            # returns the instance of Commander we got above.

            # Perform the playbook
            with tempfile.TemporaryDirectory() as temp_dir:
                a = AnsibleTestFramework(
                    base_dir=self.ansible_base_dir,
                    playbook=os.path.join("playbooks", "keeper_get.yml"),
                    inventory=os.path.join("inventory", "all"),
                    plugin_base_dir=os.path.join(self.base_dir, "..", "plugins"),
                    vars={
                        "tmp_dir": temp_dir,
                        "uid": "TRd_567FkHy-CeGsAzs8aA"
                    }
                )
                r, out, err = a.run()
                result = r[0]["localhost"]
                self.assertEqual(result["ok"], 3, "3 things didn't happen")
                self.assertEqual(result["failures"], 0, "failures was not 0")
                self.assertEqual(result["changed"], 0, "0 things didn't change")
                self.assertRegex(out, r'password_ddd', "Did not find the password in the stdout")

                a = AnsibleTestFramework(
                    base_dir=self.ansible_base_dir,
                    playbook=os.path.join("playbooks", "keeper_set.yml"),
                    inventory=os.path.join("inventory", "all"),
                    plugin_base_dir=os.path.join(self.base_dir, "..", "plugins"),
                    vars={
                        "tmp_dir": temp_dir,
                        "uid": "TRd_567FkHy-CeGsAzs8aA",
                        "new_password": "NEW PASSWORD"
                    }
                )
                r, out, err = a.run()
                print("OUT", out)
                print("ERR", err)
                result = r[0]["localhost"]
                self.assertEqual(result["ok"], 7, "7 things didn't happen")
                self.assertEqual(result["failures"], 0, "failures was not 0")
                self.assertEqual(result["changed"], 0, "0 things didn't change")
                self.assertRegex(out, r'password_ddd', "Did not find the password in the stdout")
