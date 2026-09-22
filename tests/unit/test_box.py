"""Tests for the docking search box.

The arithmetic here is easy to get wrong in ways that only show up as a failed
`write_maps` call or a grid that samples the wrong region, so the voxel and
grid-point rules are pinned against Vina's own definitions.
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from vinastudio.config import DEFAULT_SPACING, SAMPLE_DIR
from vinastudio.core.box import (
    Box,
    autobox,
    autobox_from_file,
    bounds,
    points_from_file,
    points_from_pdb,
)
from vinastudio.core.errors import InvalidInputError

SAMPLE = SAMPLE_DIR / "1iep"
LIGAND_SDF = SAMPLE / "1iep_ligand.sdf"
LIGAND_PDBQT = SAMPLE / "1iep_ligand.pdbqt"
RECEPTOR_PDB = SAMPLE / "1iep_receptorH.pdb"
DOCKING_OUTPUT = SAMPLE / "1iep_ligand_vina_out.pdbqt"

requires_samples = pytest.mark.skipif(
    not LIGAND_SDF.exists(),
    reason="run `uv run python scripts/fetch_samples.py` to fetch the 1iep data",
)

#: The box the upstream tutorial docks into.
TUTORIAL_CENTER = (15.190, 53.903, 16.917)
TUTORIAL_SIZE = (20.0, 20.0, 20.0)


# --------------------------------------------------------------------------
# construction and validation
# --------------------------------------------------------------------------


def test_a_valid_box_reports_its_derived_quantities() -> None:
    box = Box(center=TUTORIAL_CENTER, size=TUTORIAL_SIZE)

    assert box.spacing == DEFAULT_SPACING
    assert box.volume == 8000.0
    # ceil(20 / 0.375) == 54 voxels, so 55 grid points.
    assert box.voxels == (54, 54, 54)
    assert box.grid_points == (55, 55, 55)
    assert box.can_write_maps is True
    assert box.limits == (
        (5.19, 43.903, 6.917),
        (25.19, 63.903, 26.917),
    )


@pytest.mark.parametrize(
    ("size", "message"),
    [
        ((0.0, 20.0, 20.0), "must be positive"),
        ((20.0, -1.0, 20.0), "must be positive"),
        ((20.0, 20.0, 20.0), ""),
    ],
)
def test_edges_must_be_positive(size: tuple[float, float, float], message: str) -> None:
    if message:
        with pytest.raises(InvalidInputError, match=message):
            Box(center=(0.0, 0.0, 0.0), size=size)
    else:
        assert Box(center=(0.0, 0.0, 0.0), size=size).volume == 8000.0


def test_spacing_must_be_positive() -> None:
    with pytest.raises(InvalidInputError, match="spacing must be positive"):
        Box(center=(0.0, 0.0, 0.0), size=(10.0, 10.0, 10.0), spacing=0.0)


def test_non_finite_values_are_rejected() -> None:
    with pytest.raises(InvalidInputError, match="non-finite"):
        Box(center=(math.nan, 0.0, 0.0), size=(10.0, 10.0, 10.0))


def test_force_even_voxels_rounds_up_to_an_even_count() -> None:
    """`write_maps` refuses odd voxel counts, which is what the flag is for."""
    odd = Box(center=(0.0, 0.0, 0.0), size=(7.5, 20.0, 30.0))
    # 7.5 / 0.375 == 20 (even); 30 / 0.375 == 80 (even); pick a genuinely odd one.
    odd = Box(center=(0.0, 0.0, 0.0), size=(7.875, 20.0, 30.0))
    assert odd.voxels[0] == 21
    assert odd.can_write_maps is False

    even = Box(center=(0.0, 0.0, 0.0), size=(7.875, 20.0, 30.0), force_even_voxels=True)
    assert even.voxels[0] == 22
    assert even.grid_points[0] == 23  # odd grid points, as AutoGrid expects
    assert even.can_write_maps is True


def test_editing_returns_a_new_box() -> None:
    box = Box(center=(0.0, 0.0, 0.0), size=(20.0, 20.0, 20.0))
    moved = box.moved_by((1.5, -2.0, 0.5))
    resized = box.with_size((25.0, 20.0, 20.0))

    assert moved.center == (1.5, -2.0, 0.5)
    assert moved.size == box.size
    assert resized.size == (25.0, 20.0, 20.0)
    # The original is untouched: the dataclass is frozen and replace() copies.
    assert box.center == (0.0, 0.0, 0.0)


def test_containment_uses_the_full_extent() -> None:
    box = Box(center=TUTORIAL_CENTER, size=TUTORIAL_SIZE)

    assert box.contains(TUTORIAL_CENTER) is True
    assert box.contains((5.19, 43.903, 6.917)) is True  # exactly on the corner
    assert box.contains((5.0, 43.903, 6.917)) is False


def test_eight_corners_are_returned() -> None:
    box = Box(center=(0.0, 0.0, 0.0), size=(2.0, 4.0, 6.0))
    corners = box.corners()

    assert len(corners) == 8
    assert len(set(corners)) == 8
    assert min(corner[0] for corner in corners) == -1.0
    assert max(corner[2] for corner in corners) == 3.0


# --------------------------------------------------------------------------
# autobox
# --------------------------------------------------------------------------


def test_autobox_centres_on_the_points_and_adds_the_margin_per_side() -> None:
    points = [(0.0, 0.0, 0.0), (10.0, 4.0, 2.0)]
    box = autobox(points)

    assert box.center == (5.0, 2.0, 1.0)
    assert box.size == (10.0, 4.0, 2.0)


def test_extend_is_per_side_so_each_edge_grows_by_twice_it() -> None:
    """The factor of two matters: 4 A of margin per side adds 8 A to each edge."""
    points = [(0.0, 0.0, 0.0), (10.0, 10.0, 10.0)]

    box = autobox(points, extend=4.0)

    assert box.size == (18.0, 18.0, 18.0)
    assert box.center == (5.0, 5.0, 5.0)


def test_a_flat_selection_still_yields_a_usable_box() -> None:
    """A planar ligand has zero extent on one axis; a box needs a positive edge."""
    points = [(0.0, 0.0, 0.0), (10.0, 10.0, 0.0)]
    box = autobox(points)

    assert box.size[2] == DEFAULT_SPACING
    assert all(edge > 0 for edge in box.size)


def test_a_negative_margin_is_refused() -> None:
    with pytest.raises(InvalidInputError, match="must not be negative"):
        autobox([(0.0, 0.0, 0.0)], extend=-1.0)


def test_no_points_is_an_error() -> None:
    with pytest.raises(InvalidInputError, match="no coordinates"):
        autobox([])


def test_bounds_are_independent_of_point_order() -> None:
    lower, upper = bounds([(3.0, 1.0, 2.0), (-1.0, 5.0, 0.0)])

    assert lower == (-1.0, 1.0, 0.0)
    assert upper == (3.0, 5.0, 2.0)


# --------------------------------------------------------------------------
# reading coordinates
# --------------------------------------------------------------------------


@requires_samples
def test_autobox_reproduces_the_tutorial_box_centre_exactly() -> None:
    """The tutorial's box centre is this ligand's bounding-box centre.

    That is a strong check on the whole reader: the documented centre is
    (15.190, 53.903, 16.917), and deriving it from coordinates has to land on the
    same three decimals.
    """
    box, points = autobox_from_file(LIGAND_SDF, extend=6.0)

    assert points == 37  # heavy atoms of imatinib
    assert box.center == TUTORIAL_CENTER

    # The heavy-atom skeleton spans 16.7 A on its longest axis, 28.7 A with the
    # margin; the tutorial's hand-picked 20 A box is smaller than that.
    assert 25.0 < max(box.size) < 30.0


@requires_samples
def test_the_box_is_defined_by_the_heavy_atom_skeleton() -> None:
    """Hydrogen positions depend on the tool that added them, so they must not
    change the box."""
    heavy = points_from_file(LIGAND_SDF)
    with_hydrogens = points_from_file(LIGAND_SDF, include_hydrogens=True)

    assert len(heavy) == 37
    assert len(with_hydrogens) == 69

    heavy_box = autobox(heavy)
    full_box = autobox(with_hydrogens)
    assert heavy_box.volume < full_box.volume


@requires_samples
def test_a_pdbqt_pose_keeps_the_same_skeleton_as_the_sdf() -> None:
    """The PDBQT holds 3 polar hydrogens; the skeleton must still be 37 atoms."""
    from_sdf = points_from_file(LIGAND_SDF)
    from_pdbqt = points_from_file(LIGAND_PDBQT)

    assert len(from_pdbqt) == 37
    assert len(from_sdf) == 37
    assert autobox(from_pdbqt).volume == autobox(from_sdf).volume


@requires_samples
def test_a_docked_pose_can_define_the_box() -> None:
    """A pose works as an autobox source, but lands near — not on — the input's
    centre, because docking moved the conformation."""
    box, points = autobox_from_file(DOCKING_OUTPUT)

    assert points == 37
    for axis, expected in enumerate(TUTORIAL_CENTER):
        assert abs(box.center[axis] - expected) < 1.0
    # A conformation of the same molecule, so the extent is comparable.
    assert 15.0 < max(box.size) < 20.0
    assert box.center != TUTORIAL_CENTER


@requires_samples
def test_a_residue_selection_limits_the_box() -> None:
    """Autoboxing on the gatekeeper residue must give a much smaller box."""
    whole, whole_points = autobox_from_file(RECEPTOR_PDB)
    selection, selection_points = autobox_from_file(RECEPTOR_PDB, residues=("A:315",))

    assert selection_points < whole_points
    assert selection.volume < whole.volume
    assert selection_points > 0


@requires_samples
def test_an_unknown_residue_is_reported_with_the_range_available() -> None:
    with pytest.raises(InvalidInputError) as info:
        points_from_file(RECEPTOR_PDB, residues=("Z:9999",))

    message = str(info.value)
    assert "Z:9999" in message
    assert "A:225" in message and "A:498" in message


def test_a_residue_selection_against_a_ligand_format_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "ligand.sdf"
    path.write_text("fake\n")

    with pytest.raises(InvalidInputError, match="no residue information"):
        points_from_file(path, residues=("A:1",))


def test_pdb_records_without_coordinates_are_reported(tmp_path: Path) -> None:
    with pytest.raises(InvalidInputError, match="no atom records"):
        points_from_pdb("HEADER    only a header\nEND\n")


def test_unsupported_extensions_are_refused(tmp_path: Path) -> None:
    path = tmp_path / "box.xyz"
    path.write_text("1\ncomment\nH 0 0 0\n")

    with pytest.raises(InvalidInputError, match="cannot derive a box"):
        points_from_file(path)


# --------------------------------------------------------------------------
# config.txt round trip
# --------------------------------------------------------------------------


def test_config_round_trip_preserves_the_box() -> None:
    original = Box(
        center=TUTORIAL_CENTER,
        size=TUTORIAL_SIZE,
        spacing=DEFAULT_SPACING,
        force_even_voxels=True,
    )
    restored = Box.from_config(original.to_config())

    assert restored == original


def test_config_output_uses_vina_key_names() -> None:
    text = Box(center=(1.0, 2.0, 3.0), size=(20.0, 21.0, 22.0)).to_config()

    assert "center_x = 1.000" in text
    assert "center_y = 2.000" in text
    assert "center_z = 3.000" in text
    assert "size_x = 20.000" in text
    assert "spacing = 0.375" in text
    # The flag is only written when it is set, so files stay close to hand-written
    # ones.
    assert "force_even_voxels" not in text


def test_config_accepts_the_upstream_tutorial_file() -> None:
    """The exact content of the tutorial's 1iep_receptor.box.txt."""
    text = (
        "center_x = 15.190\n"
        "center_y = 53.903\n"
        "center_z = 16.917\n"
        "size_x = 20.0\n"
        "size_y = 20.0\n"
        "size_z = 20.0\n"
    )
    box = Box.from_config(text)

    assert box.center == TUTORIAL_CENTER
    assert box.size == TUTORIAL_SIZE


def test_config_ignores_keys_that_describe_a_whole_run() -> None:
    """A config.txt legitimately carries receptor, ligand and search settings."""
    text = (
        "# a whole docking run\n"
        "receptor = receptor.pdbqt\n"
        "ligand = ligand.pdbqt\n"
        "exhaustiveness = 32\n"
        "center_x = 1.0\ncenter_y = 2.0\ncenter_z = 3.0\n"
        "size_x = 20.0\nsize_y = 20.0\nsize_z = 20.0\n"
        "force_even_voxels = 1\n"
    )
    box = Box.from_config(text)

    assert box.force_even_voxels is True
    assert box.size == (20.0, 20.0, 20.0)


@pytest.mark.parametrize(
    "text",
    [
        "",
        "center_x = 1.0\ncenter_y = 2.0\n",  # missing the rest
        "center_x = a\ncenter_y = 2.0\ncenter_z = 3.0\nsize_x = 1\nsize_y = 1\nsize_z = 1\n",
    ],
)
def test_broken_configs_are_reported_clearly(text: str) -> None:
    with pytest.raises(InvalidInputError):
        Box.from_config(text)


def test_summary_shape_matches_the_api_contract() -> None:
    summary = Box(center=TUTORIAL_CENTER, size=TUTORIAL_SIZE).summary()

    assert summary["center"] == list(TUTORIAL_CENTER)
    assert summary["voxels"] == [54, 54, 54]
    assert summary["gridPoints"] == [55, 55, 55]
    assert summary["volume"] == 8000.0
    assert summary["canWriteMaps"] is True
    assert summary["forceEvenVoxels"] is False
