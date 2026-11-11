import json
import os
import tempfile
import unittest
from pathlib import Path

from minescope.configuration.settings import Settings, load_config, save_config, write_example_config
from minescope.core.errors import ConfigurationError, ValidationError
from minescope.models.server import Edition
from minescope.utils.address import parse_address, validate_host, validate_port


class AddressTests(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(parse_address("Play.Example.NET", 25565), ("play.example.net", 25565))
        self.assertEqual(parse_address("1.2.3.4:19132", 1), ("1.2.3.4", 19132))
        self.assertEqual(parse_address("[::1]:25565", 1), ("::1", 25565))
        self.assertEqual(parse_address("[::1]", 7), ("::1", 7))
        self.assertEqual(parse_address("::1", 7), ("::1", 7))

    def test_invalid(self):
        for bad in ("", " ", "host:0", "host:70000", "host:abc", "-bad.example", "a b.com",
                    "[::1", "[::1]x", "evil;rm -rf", "a" * 300, "host:"):
            with self.assertRaises(ValidationError, msg=bad):
                parse_address(bad, 25565)

    def test_port_and_host(self):
        self.assertEqual(validate_port("25565"), 25565)
        with self.assertRaises(ValidationError):
            validate_port(None)
        with self.assertRaises(ValidationError):
            validate_host("")


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())

    def write(self, doc, name="c.json"):
        p = self.dir / name
        p.write_text(json.dumps(doc), encoding="utf-8")
        return p

    def test_defaults_when_missing(self):
        s = load_config(self.dir / "missing.json")
        self.assertEqual(s.timeout, 3.0)
        self.assertEqual(load_config(None).servers, [])

    def test_full_document(self):
        p = self.write({"settings": {"timeout": 5, "concurrency": 4, "log_level": "debug"},
                        "servers": [{"name": "A", "edition": "bedrock", "address": "x.test"},
                                    {"host": "y.test", "port": 1234, "query_port": 25575}]})
        s = load_config(p)
        self.assertEqual((s.timeout, s.concurrency, s.log_level), (5.0, 4, "DEBUG"))
        self.assertEqual(s.servers[0].port, 19132)  # bedrock default port
        self.assertEqual(s.servers[0].edition, Edition.BEDROCK)
        self.assertEqual(s.servers[1].query_port, 25575)
        self.assertEqual(s.servers[1].edition, Edition.AUTO)

    def test_legacy_list_format(self):
        p = self.write([{"name": "My Java", "edition": "java", "address": "play.example.net:25565"}])
        self.assertEqual(load_config(p).servers[0].host, "play.example.net")

    def test_rejects_bad_values(self):
        cases = [{"settings": {"timeout": 0}}, {"settings": {"timeout": 999}},
                 {"settings": {"concurrency": 0}}, {"settings": {"concurrency": 1000}},
                 {"settings": {"monitor_interval": 1}}, {"settings": {"log_level": "LOUD"}},
                 {"settings": {"bogus": 1}}, {"settings": {"timeout": "fast"}},
                 {"servers": [{"edition": "java"}]}, {"servers": [{"address": "bad host"}]},
                 {"servers": [{"address": "x.test", "edition": "ps5"}]},
                 {"servers": "nope"}, {"servers": ["str"]}, 5]
        for doc in cases:
            with self.assertRaises(ConfigurationError, msg=str(doc)):
                load_config(self.write(doc))

    def test_invalid_json(self):
        p = self.dir / "bad.json"
        p.write_text("{oops", encoding="utf-8")
        with self.assertRaises(ConfigurationError):
            load_config(p)

    def test_save_roundtrip_and_example(self):
        p = write_example_config(self.dir / "ex.json")
        self.assertEqual(len(load_config(p).servers), 2)
        with self.assertRaises(ConfigurationError):
            write_example_config(p)
        write_example_config(p, overwrite=True)
        s = Settings(timeout=2.5)
        save_config(s, self.dir / "sub" / "s.json")
        self.assertEqual(load_config(self.dir / "sub" / "s.json").timeout, 2.5)
        self.assertEqual([f for f in os.listdir(self.dir / "sub") if f.endswith(".tmp")], [])


if __name__ == "__main__":
    unittest.main()
