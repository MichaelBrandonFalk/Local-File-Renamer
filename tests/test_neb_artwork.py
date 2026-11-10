import copy
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

from local_file_renamer_app import LocalFileRenamerApp
from local_file_renamer_core import RenameRow
from neb_artwork_ui import NEBArtworkDialog
from neb_artwork import parse_art_file
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

    def test_iconik_series_without_language_uses_selected_language(self):
        for variant in self.profile.types["Series"]["variants"]:
            self.put(f"CarpoolingwithJesus_ProverbsForYourSchoolLife_{variant['artTag'].upper()}_{variant['aspectRatio']}_{variant['dimensions']}.{self.profile.extensions[variant['artTag']]}")
        title = "carpooling_with_jesus_proverbs_for_your_school_life"
        for language in ("English", "Spanish"):
            with self.subTest(language=language):
                plan = self.plan("Series", title=title, language=language)
                self.assertEqual(sum(bool(row.desired_name) for row in plan.rows), len(self.profile.types["Series"]["variants"]))
                self.assertTrue(all(item.rows for item in plan.requirements))
                expected = self.profile.filename("Series", {"title": title, "language": language}, self.profile.types["Series"]["variants"][0])
                self.assertIn(expected, [row.desired_name for row in plan.rows])
        copy_artwork_plan(plan, plan.rows, str(self.output))
        self.assertEqual(len(list(self.output.iterdir())), len(plan.requirements))
        self.assertEqual(len(list(self.source.iterdir())), len(plan.requirements))

    def test_iconik_aliases_and_spacing(self):
        for suffix, tag in (("CA _3x4_1920x2560.jpg", "ca"), ("CarouselArt_7x3_2450x1100.jpg", "ca"), ("TitleTreatment_9x5_1800x1000.png", "tt")):
            with self.subTest(suffix=suffix):
                row = RenameRow(str(self.source), f"Show_{suffix}")
                parsed = parse_art_file(row, self.profile)
                self.assertIsNotNone(parsed)
                self.assertEqual(parsed.tag, tag)
                self.assertEqual(parsed.values["title"], "Show")

    def test_explicit_language_still_filters_source_art(self):
        self.put("Show_las_bg_16x9_3840x2160.jpg")
        with self.assertRaisesRegex(NEBError, "field filters"):
            self.plan("Series", language="English")

    def test_title_ending_in_short_language_code_is_not_a_language_label(self):
        for title in ("Movies", "Series"):
            parsed = parse_art_file(RenameRow(str(self.source), f"{title}_BG_16x9_3840x2160.jpg"), self.profile)
            self.assertEqual(parsed.values["title"], title)
            self.assertEqual(parsed.values["language"], "")

    def test_unrecognized_files_remain_excluded(self):
        for name in ("Show_16x9_3840x2160.jpg", "Show_RANDOM_16x9_3840x2160.jpg", "Show_BG_16x9.jpg", "notes.txt"):
            with self.subTest(name=name):
                self.assertIsNone(parse_art_file(RenameRow(str(self.source), name), self.profile))

    def test_preview_error_status_is_not_a_profile_failure(self):
        dialog = SimpleNamespace(busy=Mock(), profile_status=Mock())
        with patch("neb_artwork_ui.messagebox.showerror"):
            NEBArtworkDialog.failed(dialog, NEBError("No supported artwork"), "Preview could not be built. No files changed.")
        dialog.profile_status.set.assert_called_once_with("Preview could not be built. No files changed.")

    def test_preview_passes_exact_source_and_output_paths(self):
        value = lambda text: Mock(get=Mock(return_value=text))
        dialog = SimpleNamespace(
            folder=value("/example/ReviveSchool "), output=value("/example/Output "),
            selected_type=value("Series"), values={"title": value("Revive School"), "language": value("English")},
            recursive=value(True), required_only=value(True), group_output=value(True), reuse_shared_art=value(False),
            busy=Mock(), profile_status=Mock(), parent=Mock(), destroy=Mock(), failed=Mock(),
        )
        with patch("neb_artwork_ui.fetch_current_profile", return_value=self.profile), patch(
            "neb_artwork_ui.build_artwork_plan"
        ) as build, patch("neb_artwork_ui.background", side_effect=lambda owner, operation, done, failed: done(operation())):
            NEBArtworkDialog.build_preview(dialog)
        self.assertEqual(build.call_args.args[0], "/example/ReviveSchool ")
        self.assertEqual(dialog.parent.accept_neb_plan.call_args.args[1], "/example/Output ")

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

    def test_shared_art_reuse_accepts_lists_and_ranges(self):
        for dimensions in ("3840x2160", "1920x1080"):
            self.put(f"Show_BG_16x9_{dimensions}.jpg")
        for selection in ("1,2,3,4,5,6,7,8,9,10,11,12", "1-12"):
            with self.subTest(selection=selection):
                plan = build_artwork_plan(str(self.source), self.profile, "Episode", {"title": "Show", "season": "1", "episode": selection, "language": "English"}, reuse_shared_art=True)
                self.assertEqual(sum(bool(row.desired_name) for row in plan.rows), 24)
                self.assertTrue(all(len(item.rows) == 1 for item in plan.requirements))
                self.assertEqual({item.destination for item in plan.requirements}, {f"s01_e{number:02d}" for number in range(1, 13)})
        copy_artwork_plan(plan, plan.rows, str(self.output))
        self.assertEqual(len(list(self.output.rglob("*.jpg"))), 24)
        self.assertEqual(len(list(self.source.iterdir())), 2)
        self.assertTrue(all(path.read_bytes() == b"original artwork" for path in self.output.rglob("*.jpg")))

    def test_shared_art_reuse_requires_explicit_opt_in_and_selection(self):
        self.put("Show_BG_16x9_3840x2160.jpg")
        with self.assertRaisesRegex(NEBError, "Reuse shared artwork"):
            self.plan(season="1", episode="1-12")
        with self.assertRaisesRegex(NEBError, "Enter the episode numbers"):
            build_artwork_plan(str(self.source), self.profile, "Episode", {"title": "Show", "season": "1"}, reuse_shared_art=True)
        self.assertFalse(self.output.exists())

    def test_without_shared_mode_numbered_files_stay_with_their_episode(self):
        self.put("Show_s01_e01_eng_bg_16x9_3840x2160.jpg")
        plan = build_artwork_plan(str(self.source), self.profile, "Episode", {"title": "Show", "season": "1", "episode": "1-3", "language": "English"})
        self.assertEqual(sum(bool(row.desired_name) for row in plan.rows), 1)
        self.assertEqual(sum(not item.rows for item in plan.requirements), 5)
        self.assertTrue(all(not item.rows for item in plan.requirements if item.destination != "s01_e01"))

    def test_numbered_podcast_art_reuses_all_three_variants_for_eighteen_episodes(self):
        values = {"title": "revive_school", "season": "1", "language": "English"}
        for variant in self.profile.types["Podcast Episodes"]["variants"]:
            self.put(self.profile.filename("Podcast Episodes", {**values, "episode": "1"}, variant))
        original_names = {path.name for path in self.source.iterdir()}
        for selection in ("1-18", ",".join(str(number) for number in range(1, 19))):
            with self.subTest(selection=selection):
                plan = build_artwork_plan(str(self.source), self.profile, "Podcast Episodes", {**values, "episode": selection}, reuse_shared_art=True)
                self.assertEqual(len(plan.requirements), 54)
                self.assertEqual(sum(bool(row.desired_name) for row in plan.rows), 54)
                self.assertTrue(all(len(item.rows) == 1 for item in plan.requirements))
                self.assertEqual({item.destination for item in plan.requirements}, {f"s01_e{number:02d}" for number in range(1, 19)})
                self.assertTrue(all(row.current_name in original_names for row in plan.rows))
        copy_artwork_plan(plan, plan.rows, str(self.output))
        self.assertEqual(len(list(self.output.rglob("*.jpg"))), 54)
        self.assertEqual({path.name for path in self.source.iterdir()}, original_names)
        self.assertTrue(all(path.read_bytes() == b"original artwork" for path in self.output.rglob("*.jpg")))

    def test_reuse_can_start_after_the_source_episode_number(self):
        self.put("Show_s01_e01_eng_bg_16x9_3840x2160.jpg")
        plan = build_artwork_plan(str(self.source), self.profile, "Episode", {"title": "Show", "season": "1", "episode": "7-8", "language": "English"}, reuse_shared_art=True)
        self.assertEqual({row.desired_name for row in plan.rows if row.desired_name}, {f"show_s01_e{number:02d}_eng_bg_16x9_3840x2160.jpg" for number in (7, 8)})
        self.assertEqual({item.destination for item in plan.requirements}, {"s01_e07", "s01_e08"})

    def test_range_labelled_templates_work_for_every_episode_based_art_type(self):
        for type_name in self.profile.types:
            if not any(item["key"] == "episode" for item in self.profile.fields(type_name)):
                continue
            example = next(item for item in self.profile.document["artExamples"] if item["type"] == type_name and item["values"]["language"] == "English")
            values = {**example["values"], "title": "Revive School", "episode": "1"}
            for suffix in ("e01-e26", "e01-26"):
                with self.subTest(type_name=type_name, suffix=suffix):
                    for path in self.source.iterdir():
                        path.unlink()
                    variants = self.profile.types[type_name]["variants"]
                    for variant in variants:
                        filename = self.profile.filename(type_name, values, variant)
                        self.put(filename.replace("_e01_", f"_{suffix}_"))
                    for selection, count in (("1-26", 26), ("1,7,26", 3)):
                        plan = build_artwork_plan(str(self.source), self.profile, type_name, {**values, "episode": selection}, reuse_shared_art=True)
                        self.assertEqual(len(plan.requirements), count * len(variants))
                        self.assertTrue(all(len(item.rows) == 1 for item in plan.requirements))
                        self.assertEqual(sum(bool(row.desired_name) for row in plan.rows), count * len(variants))

    def test_range_template_infers_title_and_season_without_including_range_in_title(self):
        self.put("revive_school_s01_e01-e26_eng_bg_16x9_1920x1080.jpg")
        plan = build_artwork_plan(str(self.source), self.profile, "Episode", {"episode": "7-8", "language": "English"}, reuse_shared_art=True)
        self.assertEqual({row.desired_name for row in plan.rows if row.desired_name}, {f"revive_school_s01_e{number:02d}_eng_bg_16x9_1920x1080.jpg" for number in (7, 8)})

    def test_range_templates_require_opt_in_even_with_a_single_target_episode(self):
        self.put("revive_school_s01_e01-e26_eng_bg_16x9_1920x1080.jpg")
        for selection in ("7", "1-26"):
            with self.subTest(selection=selection), self.assertRaisesRegex(NEBError, "source filenames contain an episode range"):
                self.plan(season="1", episode=selection)

    def test_descending_source_episode_range_is_rejected(self):
        self.put("revive_school_s01_e26-e01_eng_bg_16x9_1920x1080.jpg")
        with self.assertRaisesRegex(NEBError, "ascending"):
            build_artwork_plan(str(self.source), self.profile, "Episode", {"episode": "1-26", "language": "English"}, reuse_shared_art=True)

    def test_reuse_of_multiple_numbered_sources_still_requires_conflict_selection(self):
        for episode in (1, 2):
            self.put(f"Show_s01_e{episode:02d}_eng_bg_16x9_3840x2160.jpg")
        plan = build_artwork_plan(str(self.source), self.profile, "Episode", {"title": "Show", "season": "1", "episode": "1-3", "language": "English"}, reuse_shared_art=True)
        conflicts = [item for item in plan.requirements if len(item.rows) > 1]
        self.assertEqual(len(conflicts), 3)
        self.assertTrue(all(not row.desired_name for item in conflicts for row in item.rows))
        copy_artwork_plan(plan, plan.rows, str(self.output))
        self.assertFalse(self.output.exists())

    def test_shared_episode_override_does_not_change_language_or_season_filters(self):
        for filename in ("Show_s02_e01_eng_bg_16x9_3840x2160.jpg", "Show_s01_e01_las_bg_16x9_3840x2160.jpg"):
            self.put(filename)
        with self.assertRaisesRegex(NEBError, "field filters"):
            build_artwork_plan(str(self.source), self.profile, "Episode", {"title": "Show", "season": "1", "episode": "1-3", "language": "English"}, reuse_shared_art=True)

    def test_shared_reuse_preserves_conflicts_and_supports_flat_output(self):
        self.put("Show_BG_16x9_3840x2160.jpg")
        self.put("Show_BG_16x9_3840x2160_V2.jpg")
        plan = build_artwork_plan(str(self.source), self.profile, "Episode", {"title": "Show", "season": "1", "episode": "1-2", "language": "English"}, reuse_shared_art=True, group_output=False)
        conflicts = [item for item in plan.requirements if len(item.rows) == 2]
        self.assertEqual(len(conflicts), 2)
        for item in conflicts:
            self.assertTrue(all(not row.desired_name for row in item.rows))
            plan.choose_match(item.rows[0])
        copy_artwork_plan(plan, plan.rows, str(self.output))
        self.assertEqual(len(list(self.output.glob("*.jpg"))), 2)

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

    def test_extra_type_selection_does_not_relabel_another_extra_category(self):
        variant = self.profile.types["Extras"]["variants"][0]
        filename = self.profile.filename("Extras", {"title": "Example", "language": "English", "extra_usage": "Deleted Scenes"}, variant)
        self.put(filename)
        with self.assertRaisesRegex(NEBError, "field filters"):
            self.plan("Extras", extra_usage="Behind the Scenes / Making Of")
        plan = self.plan("Extras", extra_usage="Deleted Scenes")
        self.assertIn(filename, [row.desired_name for row in plan.rows])


if __name__ == "__main__":
    unittest.main()
