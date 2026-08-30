"""Unit tests for the SKU folder-name parser -- a pure function, no
filesystem access. Cases are drawn from real folder names found while
inspecting the actual library (see PROJECT_INSTRUCTIONS.md section 4).
"""

import pytest

from patch_pos.library import parse_sku_folder_name


class TestParseSkuFolderName:
    @pytest.mark.parametrize(
        "folder_name,expected",
        [
            ("MP-P-000 - LOGO", ("MP-P-000", 0, "LOGO")),
            ("MP-P-001 - POGI", ("MP-P-001", 1, "POGI")),
            (
                "MP-P-374-LETRAN KNIGHTS HEAD 1620 CIRCULAR",
                ("MP-P-374", 374, "LETRAN KNIGHTS HEAD 1620 CIRCULAR"),
            ),
            ("MP-P-825 - HELLROADS ", ("MP-P-825", 825, "HELLROADS")),
            (
                "MP-P-353 - MAPUA CARDINAL BIRD CIRCULAR ",
                ("MP-P-353", 353, "MAPUA CARDINAL BIRD CIRCULAR"),
            ),
            ("MP-P-30 - YOU'RE THE RICE TO MY ADOBO", ("MP-P-30", 30, "YOU'RE THE RICE TO MY ADOBO")),
        ],
    )
    def test_parses_real_world_folder_names(self, folder_name, expected):
        assert parse_sku_folder_name(folder_name) == expected

    @pytest.mark.parametrize(
        "folder_name",
        [
            "BICYCLE",
            "System Volume Information",
            "MNP Patch Master List",
            "",
            "MP-P- - NO NUMBER",
        ],
    )
    def test_returns_none_for_non_product_folders(self, folder_name):
        assert parse_sku_folder_name(folder_name) is None
