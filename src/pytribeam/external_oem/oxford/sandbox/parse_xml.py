import xml.etree.ElementTree as ET
from pathlib import Path

xml_path = Path(
    r"C:\Program Files\Oxford Instruments NanoAnalysis\Plugin\OINA.Plugin.AcquisitionClient.xml"
)

tree = ET.parse(xml_path)
root = tree.getroot()

members = root.find("members")

for member in members.findall("member"):
    name = member.attrib.get("name", "")
    summary_node = member.find("summary")

    if summary_node is not None:
        summary = "".join(summary_node.itertext()).strip()
        summary = " ".join(summary.split())
    else:
        summary = ""

    if any(
        term.lower() in name.lower() or term.lower() in summary.lower()
        for term in [
            "scan",
            "region",
            "area",
            "proximity",
            "ebsd",
            "eds",
            "map",
            "line",
            "navigation",
            "profile",
        ]
    ):
        print(f"\n{name}")
        if summary:
            print(f"  {summary}")
