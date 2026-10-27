import copy
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

from local_file_renamer_app import LocalFileRenamerApp
from neb_artwork import COMBINED_TYPE, NEBError, NEBProfile, build_artwork_plan, copy_artwork_plan, episode_selection, fetch_current_profile, read_profile


class NEBArtworkTests(unittest.TestCase):
    def setUp(self):
        self.profile = read_profile()
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "source"
        self.source.mkdir()
        self.output = self.root / "output"

    def put(self, name, data=b"original artwork"):
        path = self.source / name
        path.write_bytes(data)
        return path

    def plan(self, type_name="Episode", **values):
        return build_artwork_plan(str(self.source), self.profile, type_name, {"language": "English", **values})

    def test_exact_user_title_examples(self):
        self.put("When Hope Callseng_bg_16x9_3840x2160.jpg")
        plan = self.plan("Movie")
        self.assertIn("when_hope_calls_eng_bg_16x9_3840x2160.jpg", [row.desired_name for row in plan.rows])
        for file in self.source.iterdir():
            file.unlink()
        self.put("TITLE_eng_bg_16x9_3840x2160.jpg")
        plan = self.plan("Movie", title="The Christmas Yes List")
        self.assertIn("the_christmas_yes_list_eng_bg_16x9_3840x2160.jpg", [row.desired_name for row in plan.rows])

    def test_placeholder_requires_an_explicit_title(self):
        self.put("TITLE_eng_bg_16x9_3840x2160.jpg")
        with self.assertRaisesRegex(NEBError, "correct title"):
            self.plan("Movie")
        self.assertFalse(self.output.exists())

    def test_series_and_season_share_sources_but_copy_distinct_required_sets(self):
        for variant in self.profile.types["Series"]["variants"]:
            self.put(self.profile.filename("Series", {"title": "Original Series", "language": "English"}, variant))
        originals = {file.name: file.read_bytes() for file in self.source.iterdir()}
        plan = self.plan(COMBINED_TYPE, title="When Hope Calls", season="02")
        copy_artwork_plan(plan, plan.rows, str(self.output))
        series = list((self.output / "Series").iterdir())
        season = list((self.output / "Season 02").iterdir())
        self.assertEqual(len(series), len(self.profile.types["Series"]["variants"]))
        self.assertEqual(len(season), len(self.profile.types["Season Placeholder"]["variants"]))
        self.assertTrue(all(file.name.startswith("when_hope_calls_s02_eng_") for file in season))
        self.assertEqual({file.name: file.read_bytes() for file in self.source.iterdir()}, originals)

    def test_multiple_episodes_copy_only_two_required_images_each(self):
        for episode in (1, 2):
            for dimensions in ("3840x2160", "1920x1080", "2560x1440"):
                self.put(f"TITLE_s01_e{episode:02d}_eng_bg_16x9_{dimensions}.jpg")
            self.put(f"TITLE_s01_e{episode:02d}_eng_ca_16x9_3840x2160.jpg")
        plan = self.plan(title="When Hope Calls")
        copy_artwork_plan(plan, plan.rows, str(self.output))
        files = [file for file in self.output.rglob("*") if file.is_file()]
        self.assertEqual(len(files), 4)
        for episode in (1, 2):
            self.assertEqual(len(list((self.output / f"s01_e{episode:02d}").iterdir())), 2)
        self.assertTrue(all("2560x1440" not in file.name and "_ca_" not in file.name for file in files))
        self.assertTrue(any(row.status.startswith("Excluded:") for row in plan.rows))

    def test_episode_range_reports_missing_episodes_without_creating_fake_files(self):
        for episode in (1, 2):
            for dimensions in ("3840x2160", "1920x1080"):
                self.put(f"Show_s01_e{episode:02d}_eng_bg_16x9_{dimensions}.jpg")
        plan = self.plan(episode="1-3")
        self.assertEqual(sum(row.status.startswith("Missing:") for row in plan.rows), 2)
        copy_artwork_plan(plan, plan.rows, str(self.output))
        self.assertFalse((self.output / "s01_e03").exists())

    def test_duplicate_sources_require_selection_and_copy_the_chosen_version(self):
        original = "Show_s01_e01_eng_bg_16x9_3840x2160.jpg"
        alternate = "Show_s01_e01_eng_bg_16x9_3840x2160_V2.jpg"
        self.put(original, b"old version")
        self.put(alternate, b"chosen version")
        self.put("Show_s01_e01_eng_bg_16x9_1920x1080.jpg")
        plan = self.plan()
        conflicts = [row for row in plan.rows if row.status.startswith("Conflict:")]
        self.assertEqual(len(conflicts), 2)
        self.assertTrue(all(not row.desired_name for row in conflicts))
        chosen = next(row for row in conflicts if row.current_name == alternate)
        self.assertTrue(plan.choose_match(chosen))
        copy_artwork_plan(plan, plan.rows, str(self.output))
        self.assertEqual((self.output / "s01_e01" / original.lower()).read_bytes(), b"chosen version")
        self.assertEqual((self.source / original).read_bytes(), b"old version")

    def test_removed_rows_are_not_copied(self):
        for dimensions in ("3840x2160", "1920x1080"):
            self.put(f"Show_s01_e01_eng_bg_16x9_{dimensions}.jpg")
        plan = self.plan()
        kept = [row for row in plan.rows if "3840x2160" not in row.current_name]
        copy_artwork_plan(plan, kept, str(self.output))
        self.assertEqual(len(list(self.output.rglob("*.jpg"))), 1)

    def test_required_variants_follow_an_updated_profile(self):
        document = copy.deepcopy(self.profile.document)
        episode = next(item for item in document["profile"]["types"] if item["domain"] == "art" and item["name"] == "Episode")
        episode["variants"].append({"artTag": "bg", "aspectRatio": "4x3", "dimensions": "1440x1080", "tags": []})
        for example in document["artExamples"]:
            if example["type"] == "Episode":
                example["filenames"].append(example["filenames"][0].rsplit("_bg_", 1)[0] + "_bg_4x3_1440x1080.jpg")
        updated = NEBProfile(document)
        self.put("Show_s01_e01_eng_bg_4x3_1440x1080.jpg")
        plan = build_artwork_plan(str(self.source), updated, "Episode", {"language": "English"})
        self.assertEqual(len(plan.requirements), 3)
        self.assertEqual(sum(bool(row.desired_name) for row in plan.rows), 1)
        self.assertNotEqual(updated.fingerprint, self.profile.fingerprint)

    def test_engine_conformance_changes_are_rejected(self):
        document = copy.deepcopy(self.profile.document)
        document["profile"]["rules"]["titleCase"] = "upper"
        with self.assertRaisesRegex(NEBError, "normalization has changed"):
            NEBProfile(document)

    def test_every_current_art_type_accepts_its_own_canonical_source_names(self):
        examples = {}
        for example in self.profile.document["artExamples"]:
            if example["values"]["language"] == "English":
                examples.setdefault(example["type"], example)
        for type_name, example in examples.items():
            with self.subTest(type_name=type_name):
                for file in self.source.iterdir():
                    file.unlink()
                expected = example["filenames"][0]
                self.put(expected)
                plan = self.plan(type_name)
                self.assertIn(expected, [row.desired_name for row in plan.rows])

    def test_live_fetch_validates_and_caches_only_profile_data(self):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps(self.profile.document).encode()
        cache = self.root / "cache" / "profile.json"
        with patch("neb_artwork.urlopen", return_value=response) as download:
            fresh = fetch_current_profile(cache)
        self.assertEqual(fresh.fingerprint, self.profile.fingerprint)
        self.assertTrue(cache.is_file())
        self.assertNotIn("title", download.call_args.args[0].full_url)

    def test_profile_change_blocks_copy_from_an_old_preview(self):
        app = SimpleNamespace(
            neb_plan=SimpleNamespace(profile=self.profile), run_button=Mock(), set_status=Mock(),
        )
        with patch("local_file_renamer_app.background", side_effect=lambda owner, operation, done, failed: done(SimpleNamespace(fingerprint="changed"))), patch(
            "local_file_renamer_app.messagebox.showerror"
        ) as error, patch.object(LocalFileRenamerApp, "_execute_renames") as execute:
            LocalFileRenamerApp.run_renames(app)
        error.assert_called_once()
        execute.assert_not_called()

    def test_episode_selection_rejects_invalid_ranges(self):
        self.assertEqual(episode_selection("1-3, e05"), {1, 2, 3, 5})
        for invalid in ("0", "9-2", "1-1000", "guess"):
            with self.subTest(value=invalid), self.assertRaises(NEBError):
                episode_selection(invalid)

    def test_season_override_can_reuse_series_art_in_an_s1_folder(self):
        renamed = self.root / "S1"
        self.source.rename(renamed)
        self.source = renamed
        self.put("Show_eng_bg_16x9_3840x2160.jpg")
        plan = self.plan(COMBINED_TYPE, season="02")
        self.assertTrue(any(row.desired_name == "show_s02_eng_bg_16x9_3840x2160.jpg" for row in plan.rows))

    def test_output_subfolder_cannot_escape_through_a_symlink(self):
        self.put("Show_s01_e01_eng_bg_16x9_3840x2160.jpg")
        plan = self.plan()
        self.output.mkdir()
        (self.output / "s01_e01").symlink_to(self.source, target_is_directory=True)
        with self.assertRaises(NEBError):
            copy_artwork_plan(plan, plan.rows, str(self.output))
        self.assertEqual(len(list(self.source.iterdir())), 1)


if __name__ == "__main__":
    unittest.main()
