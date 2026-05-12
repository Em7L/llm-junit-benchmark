from __future__ import annotations

"""PIT mutation-testing helpers for Maven/JUnit 5 projects."""

from collections import Counter
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET

from benchmark_pipeline.maven import run_maven_command
from benchmark_pipeline.models import PitestMutation, PitestResult


PITEST_MAVEN_VERSION = "1.23.1"
PITEST_JUNIT5_PLUGIN_VERSION = "1.2.3"


def configure_pitest_plugin(repo_root: Path) -> None:
    pom_path = repo_root / "pom.xml"
    if not pom_path.exists():
        raise FileNotFoundError(f"pom.xml not found: {pom_path}")

    tree = ET.parse(pom_path)
    root = tree.getroot()
    namespace = _namespace(root)
    ns_prefix = f"{{{namespace}}}" if namespace else ""
    ET.register_namespace("", namespace) if namespace else None

    build = _child(root, "build", ns_prefix)
    plugins = _child(build, "plugins", ns_prefix)

    plugin = _find_plugin(plugins, ns_prefix, "org.pitest", "pitest-maven")
    if plugin is None:
        plugin = ET.SubElement(plugins, f"{ns_prefix}plugin")
        ET.SubElement(plugin, f"{ns_prefix}groupId").text = "org.pitest"
        ET.SubElement(plugin, f"{ns_prefix}artifactId").text = "pitest-maven"

    _set_child_text(plugin, "version", ns_prefix, PITEST_MAVEN_VERSION)
    configuration = _child(plugin, "configuration", ns_prefix)
    _set_child_text(configuration, "timestampedReports", ns_prefix, "false")
    _set_child_text(configuration, "failWhenNoMutations", ns_prefix, "false")

    output_formats = _child(configuration, "outputFormats", ns_prefix)
    output_formats.clear()
    ET.SubElement(output_formats, f"{ns_prefix}param").text = "XML"
    ET.SubElement(output_formats, f"{ns_prefix}param").text = "HTML"

    dependencies = _child(plugin, "dependencies", ns_prefix)
    dependency = _find_dependency(dependencies, ns_prefix, "org.pitest", "pitest-junit5-plugin")
    if dependency is None:
        dependency = ET.SubElement(dependencies, f"{ns_prefix}dependency")
        ET.SubElement(dependency, f"{ns_prefix}groupId").text = "org.pitest"
        ET.SubElement(dependency, f"{ns_prefix}artifactId").text = "pitest-junit5-plugin"
    _set_child_text(dependency, "version", ns_prefix, PITEST_JUNIT5_PLUGIN_VERSION)

    tree.write(pom_path, encoding="utf-8", xml_declaration=True)


def run_pitest(repo_root: Path, maven_executable: str) -> PitestResult:
    configure_pitest_plugin(repo_root)
    command = [
        maven_executable,
        "test-compile",
        f"org.pitest:pitest-maven:{PITEST_MAVEN_VERSION}:mutationCoverage",
    ]
    completed = run_maven_command(repo_root, command)
    report_file = repo_root / "target" / "pit-reports" / "mutations.xml"
    mutations = parse_pitest_mutations(report_file)
    status_counts = dict(Counter(mutation.status for mutation in mutations))
    mutation_score = calculate_mutation_score(status_counts)
    return PitestResult(
        exit_code=completed.returncode,
        report_file=report_file.as_posix() if report_file.exists() else None,
        total_mutations=len(mutations),
        status_counts=status_counts,
        mutation_score=mutation_score,
        mutations=mutations,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def persist_pitest_reports(result: PitestResult, destination_dir: Path) -> PitestResult:
    if result.report_file is None:
        return result

    source_file = Path(result.report_file)
    source_dir = source_file.parent
    if not source_dir.exists():
        return result

    if destination_dir.exists():
        shutil.rmtree(destination_dir)
    shutil.copytree(source_dir, destination_dir)
    result.report_file = (destination_dir / source_file.name).as_posix()
    return result


def parse_pitest_mutations(report_file: Path) -> list[PitestMutation]:
    if not report_file.exists():
        return []

    try:
        root = ET.fromstring(report_file.read_text(encoding="utf-8"))
    except ET.ParseError:
        return []

    mutations: list[PitestMutation] = []
    for mutation in root.findall("mutation"):
        fields = {
            "source_file": _text(mutation, "sourceFile"),
            "mutated_class": _text(mutation, "mutatedClass"),
            "mutated_method": _text(mutation, "mutatedMethod"),
            "method_description": _text(mutation, "methodDescription"),
            "line_number": _optional_int(_text(mutation, "lineNumber")),
            "mutator": _text(mutation, "mutator"),
            "index": _optional_int(_text(mutation, "index")),
            "block": _optional_int(_text(mutation, "block")),
            "description": _text(mutation, "description"),
        }
        mutant_id = "|".join(
            [
                fields["mutated_class"],
                fields["mutated_method"],
                fields["method_description"],
                str(fields["line_number"]),
                fields["mutator"],
                str(fields["index"]),
                str(fields["block"]),
            ]
        )
        mutations.append(
            PitestMutation(
                mutant_id=mutant_id,
                detected=mutation.attrib.get("detected", "false").lower() == "true",
                status=mutation.attrib.get("status", "UNKNOWN"),
                number_of_tests_run=_optional_int(mutation.attrib.get("numberOfTestsRun", "")) or 0,
                source_file=fields["source_file"],
                mutated_class=fields["mutated_class"],
                mutated_method=fields["mutated_method"],
                method_description=fields["method_description"],
                line_number=fields["line_number"],
                mutator=fields["mutator"],
                index=fields["index"],
                block=fields["block"],
                killing_test=_text(mutation, "killingTest"),
                description=fields["description"],
            )
        )
    return mutations


def calculate_mutation_score(status_counts: dict[str, int]) -> float | None:
    killed = status_counts.get("KILLED", 0)
    scored_total = killed + status_counts.get("SURVIVED", 0) + status_counts.get("NO_COVERAGE", 0)
    return killed / scored_total if scored_total else None


def _namespace(element: ET.Element) -> str:
    if element.tag.startswith("{"):
        return element.tag[1:].split("}", 1)[0]
    return ""


def _child(parent: ET.Element, tag: str, ns_prefix: str) -> ET.Element:
    child = parent.find(f"{ns_prefix}{tag}")
    if child is None:
        child = ET.SubElement(parent, f"{ns_prefix}{tag}")
    return child


def _set_child_text(parent: ET.Element, tag: str, ns_prefix: str, value: str) -> None:
    _child(parent, tag, ns_prefix).text = value


def _find_plugin(plugins: ET.Element, ns_prefix: str, group_id: str, artifact_id: str) -> ET.Element | None:
    for plugin in plugins.findall(f"{ns_prefix}plugin"):
        if _text(plugin, "groupId", ns_prefix) == group_id and _text(plugin, "artifactId", ns_prefix) == artifact_id:
            return plugin
    return None


def _find_dependency(dependencies: ET.Element, ns_prefix: str, group_id: str, artifact_id: str) -> ET.Element | None:
    for dependency in dependencies.findall(f"{ns_prefix}dependency"):
        if _text(dependency, "groupId", ns_prefix) == group_id and _text(dependency, "artifactId", ns_prefix) == artifact_id:
            return dependency
    return None


def _text(element: ET.Element, tag: str, ns_prefix: str = "") -> str:
    child = element.find(f"{ns_prefix}{tag}")
    return (child.text or "").strip() if child is not None else ""


def _optional_int(value: str) -> int | None:
    try:
        return int(value)
    except ValueError:
        return None
