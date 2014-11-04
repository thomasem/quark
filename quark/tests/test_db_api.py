# Copyright 2013 Openstack Foundation
# All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
#  under the License.

import mock
import netaddr

from quark.db import api as db_api
from quark.db import models
from quark.tests.functional.base import BaseFunctionalTest


class TestDBAPI(BaseFunctionalTest):
    def setUp(self):
        super(TestDBAPI, self).setUp()

    def test_port_find_ip_address_id(self):
        self.context.session.query = mock.Mock()
        db_api.port_find(self.context, ip_address_id="fake")
        query_obj = self.context.session.query.return_value
        filter_fn = query_obj.options.return_value.filter
        self.assertEqual(filter_fn.call_count, 1)

    def test_ip_address_find_device_id(self):
        query_mock = mock.Mock()
        second_query_mock = mock.Mock()
        filter_mock = mock.Mock()

        self.context.session.query = query_mock
        query_mock.return_value = second_query_mock
        second_query_mock.join.return_value = filter_mock

        db_api.ip_address_find(self.context, device_id="foo")
        self.assertEqual(filter_mock.filter.call_count, 1)

    def test_ip_address_find_address_type(self):
        self.context.session.query = mock.MagicMock()
        second_query_mock = self.context.session.query.return_value
        filter_mock = second_query_mock.join.return_value

        db_api.ip_address_find(self.context, address_type="foo")
        # NOTE(thomasem): Creates sqlalchemy.sql.elements.BinaryExpression
        # when using SQLAlchemy models in expressions.
        expected_filter = models.IPAddress.address_type == "foo"
        self.assertEqual(len(filter_mock.filter.call_args[0]), 1)
        # NOTE(thomasem): Unfortunately BinaryExpression.compare isn't
        # showing to be a reliable comparison, so using the string
        # representation which dumps the associated SQL for the filter.
        self.assertEqual(str(expected_filter), str(
            filter_mock.filter.call_args[0][0]))

    def test_ip_address_find_port_id(self):
        self.context.session.query = mock.MagicMock()
        second_query_mock = self.context.session.query.return_value
        final_query_mock = second_query_mock.join.return_value

        db_api.ip_address_find(self.context, port_id="foo")
        # NOTE(thomasem): Creates sqlalchemy.sql.elements.BinaryExpression
        # when using SQLAlchemy models in expressions.
        expected_filter = models.IPAddress.ports.any(models.Port.id == "foo")
        self.assertEqual(len(final_query_mock.filter.call_args[0]), 1)
        self.assertEqual(str(expected_filter), str(
            final_query_mock.filter.call_args[0][0]))

    def test_ip_address_find_ip_address_object(self):
        ip_address = netaddr.IPAddress("192.168.10.1")
        try:
            db_api.ip_address_find(self.context, ip_address=ip_address,
                                   scope=db_api.ONE)
        except Exception as e:
            self.fail("Expected no exceptions: %s" % e)

    def test_ip_address_find_ip_address_list(self):
        ip_address = netaddr.IPAddress("192.168.10.1")
        try:
            db_api.ip_address_find(self.context, ip_address=[ip_address],
                                   scope=db_api.ONE)
        except Exception as e:
            self.fail("Expected no exceptions: %s" % e)

    def test_ip_address_deallocate(self):
        addr = models.IPAddress(id="1", deallocated=False,
                                address_type="fixed")
        new_addr = db_api.ip_address_deallocate(self.context, addr)
        self.assertTrue(new_addr['deallocated'])
        self.assertEqual(new_addr['address_type'], None)

    def test_port_associate_ip(self):
        self.context.session.add = mock.Mock()
        mock_ports = [models.Port(id=str(x), network_id="2", ip_addresses=[])
                      for x in xrange(4)]
        mock_address = models.IPAddress(id="1", address=3232235876,
                                        address_readable="192.168.1.100",
                                        subnet_id="1", network_id="2",
                                        version=4, used_by_tenant_id="1")
        r = db_api.port_associate_ip(self.context, mock_ports, mock_address)
        self.assertEqual(len(r.associations), len(mock_ports))
        for assoc, port in zip(r.associations, mock_ports):
            self.assertEqual(assoc.port_id, port.id)
            self.assertEqual(assoc.ip_address_id, mock_address.id)
            self.assertEqual(assoc.enabled, False)
        self.context.session.add.assert_called_once_with(r)

    def test_port_associate_ip_enable_port(self):
        self.context.session.add = mock.Mock()
        mock_port = models.Port(id="1", network_id="2", ip_addresses=[])
        mock_address = models.IPAddress(id="1", address=3232235876,
                                        address_readable="192.168.1.100",
                                        subnet_id="1", network_id="2",
                                        version=4, used_by_tenant_id="1")
        r = db_api.port_associate_ip(self.context, [mock_port], mock_address,
                                     enable_port="1")
        self.assertEqual(len(r.associations), 1)
        assoc = r.associations[0]
        self.assertEqual(assoc.port_id, mock_port.id)
        self.assertEqual(assoc.ip_address_id, mock_address.id)
        self.assertEqual(assoc.enabled, True)
        self.context.session.add.assert_called_once_with(r)

    def test_port_disassociate_ip(self):
        self.context.session.add = mock.Mock()
        self.context.session.delete = mock.Mock()
        mock_ports = [models.Port(id=str(x), network_id="2", ip_addresses=[])
                      for x in xrange(4)]
        mock_address = models.IPAddress(id="1", address=3232235876,
                                        address_readable="192.168.1.100",
                                        subnet_id="1", network_id="2",
                                        version=4, used_by_tenant_id="1")
        mock_assocs = []
        for p in mock_ports:
            assoc = models.PortIpAssociation()
            assoc.port_id = p.id
            assoc.port = p
            assoc.ip_address_id = mock_address.id
            assoc.ip_address = mock_address
            mock_assocs.append(assoc)

        r = db_api.port_disassociate_ip(self.context, mock_ports[1:3],
                                        mock_address)

        self.assertEqual(len(r.associations), 2)
        self.assertEqual(r.associations[0], mock_assocs[0])
        self.assertEqual(r.associations[1], mock_assocs[3])
        self.context.session.add.assert_called_once_with(r)
        self.context.session.delete.assert_has_calls(
            [mock.call(mock_assocs[1]), mock.call(mock_assocs[2])])

    @mock.patch("quark.db.api.port_disassociate_ip")
    @mock.patch("quark.db.api.port_associate_ip")
    def test_update_port_associations_for_ip(self, associate_mock,
                                             disassociate_mock):
        self.context.session.add = mock.Mock()
        self.context.session.delete = mock.Mock()
        mock_ports = [models.Port(id=str(x), network_id="2", ip_addresses=[])
                      for x in xrange(4)]
        mock_address = models.IPAddress(id="1", address=3232235876,
                                        address_readable="192.168.1.100",
                                        subnet_id="1", network_id="2",
                                        version=4, used_by_tenant_id="1")
        mock_address.ports = mock_ports
        new_port_list = mock_ports[1:3]
        new_port_list.append(models.Port(id="4", network_id="2",
                             ip_addresses=[]))
        # NOTE(thomasem): Should be the new address after associating
        # any new ports in the list.
        mock_new_address = associate_mock.return_value

        db_api.update_port_associations_for_ip(self.context,
                                               new_port_list,
                                               mock_address)

        associate_mock.assert_called_once_with(self.context,
                                               set([new_port_list[2]]),
                                               mock_address)

        disassociate_mock.assert_called_once_with(self.context,
                                                  set([mock_ports[0],
                                                       mock_ports[3]]),
                                                  mock_new_address)
