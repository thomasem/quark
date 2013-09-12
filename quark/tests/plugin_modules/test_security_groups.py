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

import contextlib

import mock
from neutron.common import exceptions
from neutron.extensions import securitygroup as sg_ext
from oslo.config import cfg

from quark.db import models
import quark.drivers.base
from quark.plugin_modules import security_groups
from quark.tests import test_quark_plugin


class TestQuarkGetSecurityGroups(test_quark_plugin.TestQuarkPlugin):
    @contextlib.contextmanager
    def _stubs(self, security_groups):
        def _make_rules(rules):
            rule_mods = []
            for rule in rules:
                r = models.SecurityGroupRule()
                r.update(dict(id=rule))
                rule_mods.append(r)
            return rule_mods

        if isinstance(security_groups, list):
            for sg in security_groups:
                sg["rules"] = _make_rules(sg["rules"])
        elif security_groups:
            security_groups["rules"] = _make_rules(security_groups["rules"])

        with mock.patch("quark.db.api.security_group_find") as db_find:
            db_find.return_value = security_groups
            yield

    def test_get_security_groups_list(self):
        group = {"name": "foo", "description": "bar",
                 "tenant_id": self.context.tenant_id, "rules": [1]}
        with self._stubs([group]):
            result = self.plugin.get_security_groups(self.context, {})
            group = result[0]
            self.assertEqual("fake", group["tenant_id"])
            self.assertEqual("foo", group["name"])
            self.assertEqual("bar", group["description"])
            rule = group["security_group_rules"][0]
            self.assertEqual(1, rule)

    def test_get_security_group(self):
        group = {"name": "foo", "description": "bar",
                 "tenant_id": self.context.tenant_id, "rules": [1]}
        with self._stubs(group):
            result = self.plugin.get_security_group(self.context, 1)
            self.assertEqual("fake", result["tenant_id"])
            self.assertEqual("foo", result["name"])
            self.assertEqual("bar", result["description"])
            rule = result["security_group_rules"][0]
            self.assertEqual(1, rule)

    def test_get_security_group_group_not_found_fails(self):
        with self._stubs(security_groups=None):
            with self.assertRaises(sg_ext.SecurityGroupNotFound):
                self.plugin.get_security_group(self.context, 1)


class TestQuarkGetSecurityGroupRules(test_quark_plugin.TestQuarkPlugin):
    @contextlib.contextmanager
    def _stubs(self, security_rules):
        if isinstance(security_rules, list):
            rules = []
            for rule in security_rules:
                r = models.SecurityGroupRule()
                r.update(rule)
                rules.append(r)
        elif security_rules is not None:
            rules = models.SecurityGroupRule()
            rules.update(security_rules)
        with mock.patch("quark.db.api.security_group_rule_find") as db_find:
            db_find.return_value = security_rules
            yield

    def test_get_security_group_rules(self):
        rule = {"id": 1, "remote_group_id": 2, "direction": "ingress",
                "port_range_min": 80, "port_range_max": 100,
                "remote_ip_prefix": None, "ethertype": "IPv4",
                "tenant_id": "foo", "protocol": "udp", "group_id": 1}
        expected = rule.copy()
        expected["security_group_id"] = expected.pop("group_id")

        with self._stubs([rule]):
            resp = self.plugin.get_security_group_rules(self.context, {})
            for key in expected.keys():
                self.assertTrue(key in resp[0])
                self.assertEqual(resp[0][key], expected[key])

    def test_get_security_group_rule(self):
        rule = {"id": 1, "remote_group_id": 2, "direction": "ingress",
                "port_range_min": 80, "port_range_max": 100,
                "remote_ip_prefix": None, "ethertype": "IPv4",
                "tenant_id": "foo", "protocol": "udp", "group_id": 1}
        expected = rule.copy()
        expected["security_group_id"] = expected.pop("group_id")

        with self._stubs(rule):
            resp = self.plugin.get_security_group_rule(self.context, 1)
            for key in expected.keys():
                self.assertTrue(key in resp)
                self.assertEqual(resp[key], expected[key])

    def test_get_security_group_rule_not_found(self):
        with self._stubs(None):
            with self.assertRaises(sg_ext.SecurityGroupRuleNotFound):
                self.plugin.get_security_group_rule(self.context, 1)


class TestQuarkUpdateSecurityGroup(test_quark_plugin.TestQuarkPlugin):
    def setUp(self):
        super(TestQuarkUpdateSecurityGroup, self).setUp()
        self.net_driver = quark.drivers.base.BaseDriver()

    def test_update_security_group(self):
        rule = models.SecurityGroupRule()
        rule.update(dict(id=1))
        group = {"name": "foo", "description": "bar",
                 "tenant_id": self.context.tenant_id, "rules": [rule]}
        updated_group = group.copy()
        updated_group["name"] = "bar"

        with contextlib.nested(
                mock.patch("quark.db.api.security_group_find"),
                mock.patch("quark.db.api.security_group_update"),
                mock.patch(
                    "quark.drivers.base.BaseDriver.update_security_group")
        ) as (db_find, db_update, update_sg):
            db_find.return_value = group
            db_update.return_value = updated_group
            update = dict(security_group=dict(name="bar"))
            resp = self.plugin.update_security_group(self.context, 1, update,
                                                     self.net_driver)
            self.assertEqual(resp["name"], updated_group["name"])

    def test_update_security_group_with_deault_security_group_id(self):
        with self.assertRaises(sg_ext.SecurityGroupCannotUpdateDefault):
            self.plugin.update_security_group(self.context,
                                              security_groups.DEFAULT_SG_UUID,
                                              None,
                                              self.net_driver)


class TestQuarkCreateSecurityGroup(test_quark_plugin.TestQuarkPlugin):
    def setUp(self, *args, **kwargs):
        super(TestQuarkCreateSecurityGroup, self).setUp(*args, **kwargs)
        cfg.CONF.set_override('quota_security_group', 1, 'QUOTAS')
        self.net_driver = quark.drivers.base.BaseDriver()

    @contextlib.contextmanager
    def _stubs(self, security_group, other=0):
        dbgroup = models.SecurityGroup()
        dbgroup.update(security_group)

        with contextlib.nested(
                mock.patch("quark.db.api.security_group_find"),
                mock.patch("quark.db.api.security_group_create"),
        ) as (db_find, db_create):
            db_find.return_value.count.return_value = other
            db_create.return_value = dbgroup
            yield db_create

    def test_create_security_group(self):
        group = {'name': 'foo', 'description': 'bar',
                 'tenant_id': self.context.tenant_id}
        expected = {'name': 'foo', 'description': 'bar',
                    'tenant_id': self.context.tenant_id,
                    'security_group_rules': []}
        with self._stubs(group) as group_create:
            result = self.plugin.create_security_group(
                self.context, {'security_group': group}, self.net_driver)
            self.assertTrue(group_create.called)
            for key in expected.keys():
                self.assertEqual(result[key], expected[key])

    def test_create_default_security_group(self):
        group = {'name': 'default', 'description': 'bar',
                 'tenant_id': self.context.tenant_id}
        with self._stubs(group) as group_create:
            with self.assertRaises(sg_ext.SecurityGroupDefaultAlreadyExists):
                self.plugin.create_security_group(
                    self.context, {'security_group': group},
                    self.net_driver)
                self.assertTrue(group_create.called)


class TestQuarkDeleteSecurityGroup(test_quark_plugin.TestQuarkPlugin):
    @contextlib.contextmanager
    def _stubs(self, security_group=None):
        self.net_driver = quark.drivers.base.BaseDriver()
        dbgroup = None
        if security_group:
            dbgroup = models.SecurityGroup()
            dbgroup.update(security_group)

        with contextlib.nested(
            mock.patch("quark.db.api.security_group_find"),
            mock.patch("quark.db.api.security_group_delete"),
            mock.patch(
                "quark.drivers.base.BaseDriver.delete_security_group")
        ) as (group_find, db_group_delete, driver_group_delete):
            group_find.return_value = dbgroup
            db_group_delete.return_value = dbgroup
            yield db_group_delete, driver_group_delete

    def test_delete_security_group(self):
        group = {'name': 'foo', 'description': 'bar', 'id': 1,
                 'tenant_id': self.context.tenant_id}
        with self._stubs(group) as (db_delete, driver_delete):
            self.plugin.delete_security_group(self.context, 1, self.net_driver)
            self.assertTrue(db_delete.called)
            driver_delete.assert_called_once_with(self.context, 1)

    def test_delete_default_security_group(self):
        group = {'name': 'default', 'id': 1,
                 'tenant_id': self.context.tenant_id}
        with self._stubs(group) as (db_delete, driver_delete):
            with self.assertRaises(sg_ext.SecurityGroupCannotRemoveDefault):
                self.plugin.delete_security_group(self.context, 1,
                                                  self.net_driver)

    def test_delete_security_group_with_ports(self):
        port = models.Port()
        group = {'name': 'foo', 'description': 'bar', 'id': 1,
                 'tenant_id': self.context.tenant_id, 'ports': [port]}
        with self._stubs(group) as (db_delete, driver_delete):
            with self.assertRaises(sg_ext.SecurityGroupInUse):
                self.plugin.delete_security_group(self.context, 1,
                                                  self.net_driver)

    def test_delete_security_group_not_found(self):
        with self._stubs() as (db_delete, driver_delete):
            with self.assertRaises(sg_ext.SecurityGroupNotFound):
                self.plugin.delete_security_group(self.context, 1,
                                                  self.net_driver)


class TestQuarkCreateSecurityGroupRule(test_quark_plugin.TestQuarkPlugin):
    def setUp(self, *args, **kwargs):
        super(TestQuarkCreateSecurityGroupRule, self).setUp(*args, **kwargs)
        cfg.CONF.set_override('quota_security_group_rule', 1, 'QUOTAS')
        cfg.CONF.set_override('quota_security_rules_per_group', 1, 'QUOTAS')
        self.rule = {'id': 1, 'ethertype': 'IPv4',
                     'security_group_id': 1, 'group': {'id': 1},
                     'protocol': None, 'port_range_min': None,
                     'port_range_max': None}
        self.expected = {
            'id': 1,
            'remote_group_id': None,
            'direction': None,
            'port_range_min': None,
            'port_range_max': None,
            'remote_ip_prefix': None,
            'ethertype': 'IPv4',
            'tenant_id': None,
            'protocol': None,
            'security_group_id': 1}
        self.net_driver = quark.drivers.base.BaseDriver()

    @contextlib.contextmanager
    def _stubs(self, rule, group):
        dbrule = models.SecurityGroupRule()
        dbrule.update(rule)
        dbrule.group_id = rule['security_group_id']
        dbgroup = None
        if group:
            dbgroup = models.SecurityGroup()
            dbgroup.update(group)

        with contextlib.nested(
                mock.patch("quark.db.api.security_group_find"),
                mock.patch("quark.db.api.security_group_rule_find"),
                mock.patch("quark.db.api.security_group_rule_create")
        ) as (group_find, rule_find, rule_create):
            group_find.return_value = dbgroup
            rule_find.return_value.count.return_value = group.get(
                'port_rules', None) if group else 0
            rule_create.return_value = dbrule
            yield rule_create

    def _test_create_security_rule(self, **ruleset):
        ruleset['tenant_id'] = self.context.tenant_id
        rule = dict(self.rule, **ruleset)
        group = rule.pop('group')
        expected = dict(self.expected, **ruleset)
        expected.pop('group', None)
        with self._stubs(rule, group) as rule_create:
            result = self.plugin.create_security_group_rule(
                self.context, {'security_group_rule': rule},
                self.net_driver)
            self.assertTrue(rule_create.called)
            for key in expected.keys():
                self.assertEqual(expected[key], result[key])

    def test_create_security_rule_IPv6(self):
        self._test_create_security_rule(ethertype='IPv6')

    def test_create_security_rule_UDP(self):
        self._test_create_security_rule(protocol=17)

    def test_create_security_rule_UDP_string(self):
        self._test_create_security_rule(protocol="UDP")

    def test_create_security_rule_bad_string_fail(self):
        self.assertRaises(sg_ext.SecurityGroupRuleInvalidProtocol,
                          self._test_create_security_rule, protocol="DERP")

    def test_create_security_rule_TCP(self):
        self._test_create_security_rule(protocol=6)

    def test_create_security_rule_remote_ip(self):
        self._test_create_security_rule(remote_ip_prefix='192.168.0.1')

    def test_create_security_rule_remote_group(self):
        self._test_create_security_rule(remote_group_id=2)

    def test_create_security_rule_port_range_invalid_ranges_fails(self):
        with self.assertRaises(exceptions.InvalidInput):
            self._test_create_security_rule(protocol=6, port_range_min=0)

    def test_create_security_group_no_proto_with_ranges_fails(self):
        with self.assertRaises(sg_ext.SecurityGroupProtocolRequiredWithPorts):
            self._test_create_security_rule(protocol=None, port_range_min=0)
        with self.assertRaises(Exception):
            self._test_create_security_rule(
                protocol=6, port_range_min=1, port_range_max=0)

    def test_create_security_rule_remote_conflicts(self):
        with self.assertRaises(Exception):
            self._test_create_security_rule(remote_ip_prefix='192.168.0.1',
                                            remote_group_id='0')

    def test_create_security_rule_min_greater_than_max_fails(self):
        with self.assertRaises(sg_ext.SecurityGroupInvalidPortRange):
            self._test_create_security_rule(protocol=6, port_range_min=10,
                                            port_range_max=9)

    def test_create_security_rule_no_group(self):
        with self.assertRaises(sg_ext.SecurityGroupNotFound):
            self._test_create_security_rule(group=None)

    def test_create_security_rule_group_at_max(self):
        with self.assertRaises(exceptions.OverQuota):
            self._test_create_security_rule(
                group={'id': 1, 'rules': [models.SecurityGroupRule()]})


class TestQuarkDeleteSecurityGroupRule(test_quark_plugin.TestQuarkPlugin):
    @contextlib.contextmanager
    def _stubs(self, rule={}, group={'id': 1}):
        self.net_driver = quark.drivers.base.BaseDriver()
        dbrule = None
        dbgroup = None
        if group:
            dbgroup = models.SecurityGroup()
            dbgroup.update(group)
        if rule:
            dbrule = models.SecurityGroupRule()
            dbrule.update(dict(rule, group=dbgroup))

        with contextlib.nested(
                mock.patch("quark.db.api.security_group_find"),
                mock.patch("quark.db.api.security_group_rule_find"),
                mock.patch("quark.db.api.security_group_rule_delete"),
                mock.patch(
                    "quark.drivers.base.BaseDriver.delete_security_group_rule")
        ) as (group_find, rule_find, db_group_delete, driver_group_delete):
            group_find.return_value = dbgroup
            rule_find.return_value = dbrule
            yield db_group_delete, driver_group_delete

    def test_delete_security_group_rule(self):
        rule = {'id': 1, 'security_group_id': 1, 'ethertype': 'IPv4',
                'protocol': 6, 'port_range_min': 0, 'port_range_max': 10,
                'direction': 'ingress', 'tenant_id': self.context.tenant_id}
        expected = {
            'id': 1, 'ethertype': 'IPv4', 'security_group_id': 1,
            'direction': 'ingress', 'port_range_min': 0, 'port_range_max': 10,
            'remote_group_id': None, 'remote_ip_prefix': None,
            'tenant_id': self.context.tenant_id, 'protocol': 6}

        with self._stubs(dict(rule, group_id=1)) as (db_delete, driver_delete):
            self.plugin.delete_security_group_rule(self.context, 1,
                                                   self.net_driver)
            self.assertTrue(db_delete.called)
            driver_delete.assert_called_once_with(self.context, 1,
                                                  expected)

    def test_delete_security_group_rule_rule_not_found(self):
        with self._stubs() as (db_delete, driver_delete):
            with self.assertRaises(sg_ext.SecurityGroupRuleNotFound):
                self.plugin.delete_security_group_rule(self.context, 1,
                                                       self.net_driver)

    def test_delete_security_group_rule_group_not_found(self):
        rule = {'id': 1, 'security_group_id': 1, 'ethertype': 'IPv4'}
        with self._stubs(dict(rule, group_id=1),
                         None) as (db_delete, driver_delete):
            with self.assertRaises(sg_ext.SecurityGroupNotFound):
                self.plugin.delete_security_group_rule(self.context, 1,
                                                       self.net_driver)
