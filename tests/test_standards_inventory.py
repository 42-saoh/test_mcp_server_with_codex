from app.services.standards_inventory import collect_inventory, scan_standards_coverage


def test_collect_inventory_has_expected_categories() -> None:
    inventory = collect_inventory()

    assert "dynamic_sql" in inventory["tags"]
    assert "IMP_DYN_SQL" in inventory["risks"]["migration_impacts"]
    assert "PRF_SELECT_STAR" in inventory["risks"]["performance"]
    assert "RSN_LINKED_SERVER" in inventory["risks"]["db_dependency"]
    assert "TPL_VALIDATE_REQUIRED_PARAM" in inventory["templates"]
    assert any(item["id"] == "PAT_SERVICE_LAYER_TX" for item in inventory["patterns"])


def test_scan_standards_coverage_no_missing_core_categories() -> None:
    result = scan_standards_coverage("standards")
    coverage = result["coverage"]

    assert coverage["tags"]["missing"] == 0
    assert coverage["pattern_ids"]["missing"] == 0
    assert coverage["template_ids"]["missing"] == 0
