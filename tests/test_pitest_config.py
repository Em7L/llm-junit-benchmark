from __future__ import annotations

import shutil
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

import _path  # noqa: F401

from benchmark_pipeline.tools.pitest import (
    PITEST_JUNIT5_PLUGIN_VERSION,
    PITEST_MAVEN_VERSION,
    configure_pitest_plugin,
)


class TestPitestConfig(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path("run_outputs/.unit-tests/pitest-config")
        if self.root.exists():
            shutil.rmtree(self.root)
        self.root.mkdir(parents=True)

    def tearDown(self) -> None:
        if self.root.exists():
            shutil.rmtree(self.root)

    def test_configure_pitest_plugin_adds_plugin_dependency_and_output_formats(self) -> None:
        pom = self.root / "pom.xml"
        pom.write_text(
            """<project xmlns="http://maven.apache.org/POM/4.0.0">
  <modelVersion>4.0.0</modelVersion>
  <groupId>com.example</groupId>
  <artifactId>demo</artifactId>
  <version>1.0-SNAPSHOT</version>
</project>
""",
            encoding="utf-8",
        )

        configure_pitest_plugin(self.root)

        root = ET.parse(pom).getroot()
        ns = {"m": "http://maven.apache.org/POM/4.0.0"}
        plugin = root.find(".//m:plugin[m:artifactId='pitest-maven']", ns)

        self.assertIsNotNone(plugin)
        assert plugin is not None
        self.assertEqual(plugin.findtext("m:groupId", namespaces=ns), "org.pitest")
        self.assertEqual(plugin.findtext("m:version", namespaces=ns), PITEST_MAVEN_VERSION)
        self.assertEqual(plugin.findtext(".//m:timestampedReports", namespaces=ns), "false")
        self.assertEqual(plugin.findtext(".//m:failWhenNoMutations", namespaces=ns), "false")
        self.assertEqual(
            [element.text for element in plugin.findall(".//m:outputFormats/m:param", ns)],
            ["XML", "HTML"],
        )
        self.assertEqual(
            plugin.findtext(".//m:dependency[m:artifactId='pitest-junit5-plugin']/m:version", namespaces=ns),
            PITEST_JUNIT5_PLUGIN_VERSION,
        )

    def test_configure_pitest_plugin_is_idempotent(self) -> None:
        pom = self.root / "pom.xml"
        pom.write_text("<project><modelVersion>4.0.0</modelVersion></project>", encoding="utf-8")

        configure_pitest_plugin(self.root)
        configure_pitest_plugin(self.root)

        root = ET.parse(pom).getroot()
        plugins = root.findall(".//plugin[artifactId='pitest-maven']")
        dependencies = root.findall(".//dependency[artifactId='pitest-junit5-plugin']")

        self.assertEqual(len(plugins), 1)
        self.assertEqual(len(dependencies), 1)


if __name__ == "__main__":
    unittest.main()
