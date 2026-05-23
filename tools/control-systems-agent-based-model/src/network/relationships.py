from enum import Enum, auto

class RelationshipType(Enum):
    """Edge types in the FAIR-CAM network."""

    # Asset relationships
    TECH_HOSTS_BUSINESS = auto()
    TECH_CONNECTS_TECH = auto()

    # DSC relationships
    DSC_AFFECTS_PERSONNEL = auto()
    DSC_AFFECTS_CONTROL = auto()

    # VMC relationships (expanded)
    VMC_REDUCES_CHANGE_FREQ = auto()
    VMC_REDUCES_VAR_PROB = auto()
    VMC_MONITORS = auto()
    VMC_REMEDIATES = auto()

    VMC_THREAT_INTEL = auto()
    VMC_SELECTS_TREATMENT = auto()
    VMC_IMPLEMENTS_REMEDIATION = auto()

    # LEC relationships
    LEC_PROTECTS_ASSET = auto()

    # Personnel relationships
    PERSONNEL_MANAGES = auto()
    PERSONNEL_PEERS = auto()
    PERSONNEL_ACCESSES = auto()

    # Threat relationships
    THREAT_COMPROMISES = auto()


RELATIONSHIP_CONSTRAINTS = {
    RelationshipType.TECH_HOSTS_BUSINESS: ("TechAsset", "BusinessAsset"),
    RelationshipType.TECH_CONNECTS_TECH: ("TechAsset", "TechAsset"),

    RelationshipType.DSC_AFFECTS_PERSONNEL: ("DSCAgent", "PersonnelAgent"),
    RelationshipType.DSC_AFFECTS_CONTROL: ("DSCAgent", "ControlAgent"),

    RelationshipType.VMC_REDUCES_CHANGE_FREQ: ("VMCAgent", "ControlAgent"),
    RelationshipType.VMC_REDUCES_VAR_PROB: ("VMCAgent", "ControlAgent"),
    RelationshipType.VMC_MONITORS: ("VMCAgent", "ControlAgent"),
    RelationshipType.VMC_REMEDIATES: ("VMCAgent", "ControlAgent"),

    RelationshipType.VMC_THREAT_INTEL: ("VMCAgent", "ControlAgent"),
    RelationshipType.VMC_SELECTS_TREATMENT: ("VMCAgent", "ControlAgent"),
    RelationshipType.VMC_IMPLEMENTS_REMEDIATION: ("VMCAgent", "ControlAgent"),

    RelationshipType.LEC_PROTECTS_ASSET: ("LECAgent", "Asset"),

    RelationshipType.PERSONNEL_MANAGES: ("PersonnelAgent", "PersonnelAgent"),
    RelationshipType.PERSONNEL_PEERS: ("PersonnelAgent", "PersonnelAgent"),
    RelationshipType.PERSONNEL_ACCESSES: ("PersonnelAgent", "ControlAgent"),

    RelationshipType.THREAT_COMPROMISES: ("ThreatAgent", "TechAsset"),
}