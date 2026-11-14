"""Regression tests for the scraper rewrite and the stage 2 ledger."""

from __future__ import annotations

import inspect

import pytest

from src.job_ledger import (
    JobLedger,
    cross_platform_key,
    fingerprint,
    normalise_for_matching,
)
from src.scrapers import bayt, indeed, jobzella, linkedin, wuzzuf
from src.scrapers.common import annotate_cross_platform_duplicates
from src.scrapers.engine import CardSelectors, FetcherKind, SourceConfig, collect
from src.scrapers.extraction import clean_text, extract_json_ld_postings, strip_query
from src.scrapers.runner import get_sources


class FakeFetcher:
    def __init__(self, html: str | None = None, error: str | None = None) -> None:
        self._html, self._error = html, error

    def fetch(self, url: str) -> str:
        if self._error:
            raise RuntimeError(self._error)
        assert self._html is not None
        return self._html


def _undefined_attribute_bases(source: str) -> set[str]:
    """Names used as `x.y` that are never imported, assigned or a parameter.

    This is the exact bug class that killed the LinkedIn scraper: `time.sleep`
    and `re.sub` were called in a module that imported neither. A plain string
    search is not enough -- it matches docstrings too -- so this walks the AST
    and only looks at real code.
    """
    import ast
    import builtins

    tree = ast.parse(source)
    defined: set[str] = set(dir(builtins))

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                defined.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                defined.add(alias.asname or alias.name)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            defined.add(node.name)
            args = node.args
            for arg in (*args.posonlyargs, *args.args, *args.kwonlyargs):
                defined.add(arg.arg)
            if args.vararg:
                defined.add(args.vararg.arg)
            if args.kwarg:
                defined.add(args.kwarg.arg)
        elif isinstance(node, ast.ClassDef):
            defined.add(node.name)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            defined.add(node.id)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            defined.add(node.name)

    used: set[str] = {
        node.value.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)
    }
    return used - defined


def make_source(**overrides: object) -> SourceConfig:
    defaults: dict[str, object] = {
        "name": "testsite",
        "platform_label": "TestSite",
        "fetcher": FetcherKind.STATIC,
        "base_url": "https://example.com",
        "search_url_template": "https://example.com/s?q={keyword}&l={location}&start={start}",
        "try_json_ld": True,
        "min_expected_results": 1,
        "selectors": CardSelectors(
            card=["li.job"], title=["h3"], title_link=["a.job-link"],
            company=["span.company"], location=["span.loc"],
        ),
    }
    defaults.update(overrides)
    return SourceConfig.model_validate(defaults)


# ===========================================================================
# The three fatal bugs found in the uploaded code
# ===========================================================================
class TestFatalBugs:
    """All five scrapers must actually return a list of jobs."""

    @pytest.mark.parametrize(
        "module,func_name",
        [
            (wuzzuf, "scrape_wuzzuf"),
            (linkedin, "scrape_linkedin"),
            (indeed, "scrape_indeed"),
            (bayt, "scrape_bayt"),
            (jobzella, "scrape_jobzella"),
        ],
    )
    def test_scraper_module_has_no_undefined_names(self, module, func_name) -> None:
        """linkedin.py used `time.sleep` and `re.sub` without importing them.

        The NameError was swallowed by a broad `except Exception`, so LinkedIn
        returned zero jobs on every single run while logging a generic
        failure message.
        """
        undefined = _undefined_attribute_bases(inspect.getsource(module))
        assert not undefined, (
            f"{module.__name__} uses {sorted(undefined)} without importing them"
        )

    @pytest.mark.parametrize(
        "func",
        [
            wuzzuf.scrape_wuzzuf,
            linkedin.scrape_linkedin,
            indeed.scrape_indeed,
            bayt.scrape_bayt,
            jobzella.scrape_jobzella,
        ],
    )
    def test_scraper_never_returns_none(self, func, monkeypatch) -> None:
        """bayt.py and jobzella.py had no `return` and returned None.

        unified.py then called `.extend(None)`, raising TypeError, which was
        caught and logged -- so both boards contributed nothing, always.
        """
        monkeypatch.setattr(
            "src.scrapers.runner.ScraplingFetcher",
            lambda *a, **k: FakeFetcher("<html><body></body></html>"),
        )
        result = func("AI Engineer", "Egypt", True, True)
        assert result is not None
        assert isinstance(result, list)

    def test_every_configured_source_loads(self) -> None:
        sources = get_sources()
        assert set(sources) == {"wuzzuf", "linkedin", "indeed", "bayt", "jobzella"}


# ===========================================================================
# Ported stage 0/1 guarantees
# ===========================================================================
class TestExtractionGuarantees:
    def test_hyphenated_names_survive(self) -> None:
        assert clean_text("E-finance") == "E-finance"
        assert clean_text("Al-Ahly Momkn") == "Al-Ahly Momkn"

    def test_blank_becomes_none(self) -> None:
        assert clean_text("   ") is None
        assert clean_text("\u200b") is None

    def test_keyword_is_percent_encoded(self) -> None:
        url = make_source().build_url("AI Engineer & ML", "Cairo, Egypt")
        assert "AI+Engineer+%26+ML" in url
        assert "Cairo%2C+Egypt" in url

    def test_arabic_keyword_is_encoded(self) -> None:
        assert " " not in make_source().build_url("مهندس ذكاء اصطناعي", "مصر")

    def test_missing_company_is_not_guessed(self) -> None:
        """The old fallback stored "Cairo, Egypt" and "Full Time" as companies."""
        page = """
        <ul><li class="job">
          <h3>AI Engineer</h3><a class="job-link" href="/jobs/42">view</a>
          <span class="loc">Cairo, Egypt</span><span>Full Time</span>
        </li></ul>
        """
        result = collect(
            make_source(try_json_ld=False), "AI Engineer", "Egypt", FakeFetcher(page)
        )
        assert result.jobs[0]["Company"] == "N/A"

    def test_company_link_is_not_stored_as_job_link(self) -> None:
        page = '<ul><li class="job"><h3>AI Engineer</h3><a href="/company/acme">Acme</a></li></ul>'
        result = collect(
            make_source(try_json_ld=False), "AI Engineer", "Egypt", FakeFetcher(page)
        )
        assert result.jobs[0]["Link"] == "N/A"

    def test_tracking_params_are_stripped(self) -> None:
        assert strip_query("https://x.com/jobs/view/1?refId=a&trk=b") == "https://x.com/jobs/view/1"

    def test_json_ld_is_preferred_and_broken_blocks_skipped(self) -> None:
        page = """
        <html><head>
        <script type="application/ld+json">
        {"@graph":[{"@type":"WebSite","name":"skip"},
         {"@type":"JobPosting","title":"Senior AI Engineer",
          "hiringOrganization":{"name":"E-finance"},
          "url":"https://example.com/jobs/1"}]}
        </script>
        <script type="application/ld+json">{ broken </script>
        </head><body></body></html>
        """
        assert len(extract_json_ld_postings(page)) == 1
        result = collect(make_source(), "AI Engineer", "Egypt", FakeFetcher(page))
        assert result.jobs[0]["extraction_method"] == "json_ld"
        assert result.jobs[0]["Company"] == "E-finance"


class TestHealthReporting:
    def test_no_cards_is_reported_as_broken(self) -> None:
        result = collect(
            make_source(try_json_ld=False), "AI Engineer", "Egypt",
            FakeFetcher("<html><body></body></html>"),
        )
        assert result.status == "broken_cards"
        assert not result.is_healthy

    def test_site_saying_no_matches_is_not_broken(self) -> None:
        """Indeed returned zero because it had zero, not because we broke.

        The first version of this report called that a stale selector.
        """
        source = make_source(
            try_json_ld=False, no_results_markers=["did not match any jobs"]
        )
        page = "<html><body>The search did not match any jobs.</body></html>"
        result = collect(source, "AI Engineer", "Egypt", FakeFetcher(page))
        assert result.status == "no_results"
        assert result.is_healthy

    def test_cards_without_titles_is_broken_fields(self) -> None:
        page = '<ul><li class="job"><span class="company">Acme</span></li></ul>'
        result = collect(
            make_source(try_json_ld=False), "AI Engineer", "Egypt", FakeFetcher(page)
        )
        assert result.status == "broken_fields"
        assert result.cards_seen == 1
        assert result.titles_found == 0

    def test_fetch_failure_is_recorded(self) -> None:
        result = collect(
            make_source(), "AI Engineer", "Egypt", FakeFetcher(error="timeout")
        )
        assert result.status == "failed"
        assert "timeout" in result.fatal_error

    def test_loose_board_search_is_healthy_not_degraded(self) -> None:
        """Bayt returns 30 cards for "AI Engineer", of which one is relevant.

        Extraction is fine; the board's search is loose. Judging health on
        result volume produced a false DEGRADED here on real data.
        """
        cards = "".join(
            f'<li class="job"><h3>{t}</h3><a class="job-link" href="/j/{i}">x</a></li>'
            for i, t in enumerate(
                ["Lawyer", "Receptionist", "Professional Driver",
                 "Account Manager - AI Solutions"]
            )
        )
        from src.scrapers.common import _is_relevant_job

        result = collect(
            make_source(try_json_ld=False), "AI Engineer", "Egypt",
            FakeFetcher(f"<ul>{cards}</ul>"),
            relevance_filter=_is_relevant_job,
        )
        assert result.status == "ok"
        assert result.titles_found == 4
        assert len(result.jobs) == 1
        assert result.jobs[0]["Title"] == "Account Manager - AI Solutions"


# ===========================================================================
# Stage 2
# ===========================================================================
class TestDuplicateMarking:
    def test_cross_platform_duplicates_are_marked_not_removed(self) -> None:
        jobs = [
            {"Platform": "Wuzzuf", "Title": "Senior AI Engineer", "Company": "E-finance", "Link": "https://w/1"},
            {"Platform": "LinkedIn", "Title": "AI Engineer, Senior", "Company": "E-finance", "Link": "https://l/2"},
            {"Platform": "Bayt", "Title": "Data Analyst", "Company": "Other", "Link": "https://b/3"},
        ]
        annotated = annotate_cross_platform_duplicates(jobs)

        assert len(annotated) == 3, "duplicates must be kept, not collapsed"
        assert annotated[0]["duplicate_group"] == annotated[1]["duplicate_group"]
        assert annotated[0]["also_on"] == ["LinkedIn"]
        assert annotated[1]["also_on"] == ["Wuzzuf"]
        assert "duplicate_group" not in annotated[2]

    def test_both_application_links_are_preserved(self) -> None:
        jobs = [
            {"Platform": "Wuzzuf", "Title": "ML Engineer", "Company": "Acme", "Link": "https://w/1"},
            {"Platform": "LinkedIn", "Title": "ML Engineer", "Company": "Acme", "Link": "https://l/2"},
        ]
        links = {j["Link"] for j in annotate_cross_platform_duplicates(jobs)}
        assert links == {"https://w/1", "https://l/2"}

    def test_unknown_company_does_not_group(self) -> None:
        """Two unrelated jobs with Company="N/A" must not be called duplicates."""
        jobs = [
            {"Platform": "Wuzzuf", "Title": "AI Engineer", "Company": "N/A", "Link": "https://w/1"},
            {"Platform": "Bayt", "Title": "AI Engineer", "Company": "N/A", "Link": "https://b/2"},
        ]
        assert all("duplicate_group" not in j for j in annotate_cross_platform_duplicates(jobs))


class TestNormalisation:
    def test_word_order_and_noise_are_ignored(self) -> None:
        assert normalise_for_matching("Senior AI Engineer (Remote)") == normalise_for_matching(
            "AI Engineer, Senior - remote"
        )

    def test_different_roles_do_not_collide(self) -> None:
        assert normalise_for_matching("AI Engineer") != normalise_for_matching("Data Engineer")

    def test_platform_is_part_of_the_fingerprint(self) -> None:
        base = {"Title": "AI Engineer", "Company": "Acme"}
        assert fingerprint({**base, "Platform": "Wuzzuf"}) != fingerprint(
            {**base, "Platform": "LinkedIn"}
        )

    def test_role_key_ignores_platform(self) -> None:
        base = {"Title": "AI Engineer", "Company": "Acme"}
        assert cross_platform_key({**base, "Platform": "Wuzzuf"}) == cross_platform_key(
            {**base, "Platform": "LinkedIn"}
        )


class TestLedger:
    @pytest.fixture
    def ledger(self, tmp_path):
        instance = JobLedger(tmp_path / "ledger.db")
        yield instance
        instance.close()

    def test_first_run_marks_everything_new(self, ledger) -> None:
        jobs = [{"Platform": "Wuzzuf", "Title": "AI Engineer", "Company": "Acme", "Link": "https://w/1"}]
        assert ledger.annotate(jobs)[0]["is_new"] is True

    def test_second_run_marks_nothing_new(self, ledger) -> None:
        job = {"Platform": "Wuzzuf", "Title": "AI Engineer", "Company": "Acme", "Link": "https://w/1"}
        ledger.annotate([dict(job)])
        assert ledger.annotate([dict(job)])[0]["is_new"] is False

    def test_first_seen_at_is_stable_across_runs(self, ledger) -> None:
        job = {"Platform": "Wuzzuf", "Title": "AI Engineer", "Company": "Acme", "Link": "https://w/1"}
        first = ledger.annotate([dict(job)])[0]["first_seen_at"]
        assert ledger.annotate([dict(job)])[0]["first_seen_at"] == first

    def test_only_genuinely_new_jobs_are_flagged(self, ledger) -> None:
        old = {"Platform": "Wuzzuf", "Title": "AI Engineer", "Company": "Acme", "Link": "https://w/1"}
        ledger.annotate([dict(old)])

        batch = [dict(old), {"Platform": "Bayt", "Title": "ML Engineer", "Company": "Beta", "Link": "https://b/2"}]
        annotated = ledger.annotate(batch)
        assert [j["is_new"] for j in annotated] == [False, True]
        assert len(ledger.new_only(annotated)) == 1

    def test_ledger_survives_a_reopen(self, tmp_path) -> None:
        job = {"Platform": "Wuzzuf", "Title": "AI Engineer", "Company": "Acme", "Link": "https://w/1"}
        first = JobLedger(tmp_path / "l.db")
        first.annotate([dict(job)])
        first.close()

        second = JobLedger(tmp_path / "l.db")
        assert second.annotate([dict(job)])[0]["is_new"] is False
        second.close()

    def test_same_role_on_two_boards_is_two_ledger_entries(self, ledger) -> None:
        jobs = [
            {"Platform": "Wuzzuf", "Title": "AI Engineer", "Company": "Acme", "Link": "https://w/1"},
            {"Platform": "LinkedIn", "Title": "AI Engineer", "Company": "Acme", "Link": "https://l/2"},
        ]
        annotated = ledger.annotate(jobs)
        assert all(j["is_new"] for j in annotated)
        assert ledger.stats() == {"total_listings": 2, "distinct_roles": 1}


# ===========================================================================
# Relevance filter -- substring false positives
# ===========================================================================
class TestRelevanceFilter:
    """`"ai" in "detailing"` used to make every one of these a match."""

    @pytest.mark.parametrize(
        "title",
        [
            "Car Detailing Technician",
            "Retail Manager",
            "Email Marketing Specialist",
            "Maintenance Engineer",
            "Training Coordinator",
            "Chairman Assistant",
            "HTML Developer",
        ],
    )
    def test_two_letter_synonyms_do_not_match_inside_words(self, title) -> None:
        from src.scrapers.common import _is_relevant_job

        assert not _is_relevant_job("AI Engineer", title)

    @pytest.mark.parametrize(
        "title",
        [
            "AI Engineer",
            "Senior ML Engineer",
            "Machine Learning Engineer",
            "Deep Learning Researcher",
            "Account Manager - AI Solutions",
        ],
    )
    def test_genuine_matches_still_pass(self, title) -> None:
        from src.scrapers.common import _is_relevant_job

        assert _is_relevant_job("AI Engineer", title)


class TestCompanyCleaning:
    def test_dangling_separators_are_trimmed(self) -> None:
        from src.scrapers.extraction import clean_company

        assert clean_company("The-Code - ") == "The-Code"
        assert clean_company(" | Acme Corp |") == "Acme Corp"

    def test_internal_hyphens_survive(self) -> None:
        from src.scrapers.extraction import clean_company

        assert clean_company("E-finance") == "E-finance"
        assert clean_company("Al-Ahly Momkn") == "Al-Ahly Momkn"

    def test_separator_only_value_is_none(self) -> None:
        from src.scrapers.extraction import clean_company

        assert clean_company("  -  ") is None


class TestNoResultsMarkers:
    """A marker that can appear on the wrong page hides real breakage."""

    def test_generic_marker_would_mask_a_wrong_page(self) -> None:
        """Jobzella served an unrelated profile page containing "no results".

        With a generic marker that read as `no_results` ("nothing is broken"),
        which is exactly the false reassurance this whole health model exists
        to prevent.
        """
        profile_page = "<html><body>Professional Summary. No results to show.</body></html>"

        lenient = make_source(try_json_ld=False, no_results_markers=["no results"])
        assert collect(lenient, "AI Engineer", "Egypt", FakeFetcher(profile_page)).status == (
            "no_results"
        )

        strict = make_source(
            try_json_ld=False, no_results_markers=["no jobs match your search"]
        )
        assert collect(strict, "AI Engineer", "Egypt", FakeFetcher(profile_page)).status == (
            "broken_cards"
        )

    def test_configured_markers_are_specific(self) -> None:
        """Guard against someone adding a two-word marker later."""
        for name, source in get_sources().items():
            for marker in source.no_results_markers:
                assert len(marker.split()) >= 3, (
                    f"{name}: marker {marker!r} is too generic to be safe"
                )


class TestStrategyMerging:
    """All extraction strategies run; none is authoritative for running first."""

    STRAY_JSON_LD_PLUS_CARDS = """
    <html><head>
    <script type="application/ld+json">
    {"@type":"JobPosting","title":"Technical Office Engineer",
     "hiringOrganization":{"name":"Old Corp"},"datePosted":"2023-01-28"}
    </script>
    </head><body>
    <ul>
      <li class="job"><h3>AI Engineer</h3><a class="job-link" href="/j/1">x</a>
        <span class="company">Areeb</span></li>
      <li class="job"><h3>Senior ML Engineer</h3><a class="job-link" href="/j/2">x</a>
        <span class="company">Valeo</span></li>
    </ul></body></html>
    """

    def test_one_stray_posting_does_not_suppress_the_card_path(self) -> None:
        """This is exactly what hid 119 Jobzella results behind one 2023 job.

        The old code stopped as soon as any strategy produced a title.
        """
        result = collect(
            make_source(), "AI Engineer", "Egypt",
            FakeFetcher(self.STRAY_JSON_LD_PLUS_CARDS),
        )
        titles = {job["Title"] for job in result.jobs}
        assert "AI Engineer" in titles
        assert "Senior ML Engineer" in titles
        assert result.cards_seen == 2

    def test_the_same_listing_from_two_strategies_is_counted_once(self) -> None:
        page = """
        <html><head>
        <script type="application/ld+json">
        {"@type":"JobPosting","title":"AI Engineer",
         "hiringOrganization":{"name":"Areeb"},"url":"https://x/1"}
        </script></head><body>
        <ul><li class="job"><h3>AI Engineer</h3><a class="job-link" href="/j/1">x</a>
          <span class="company">Areeb</span></li></ul>
        </body></html>
        """
        result = collect(make_source(), "AI Engineer", "Egypt", FakeFetcher(page))
        assert result.titles_found == 1
        assert len(result.jobs) == 1


class TestNextData:
    PAGE = """
    <html><body><script id="__NEXT_DATA__" type="application/json">
    {"props":{"pageProps":{"jobs":[
      {"id":12026,"position":{"name":"AI Engineer"},
       "company":{"title":"PANNELLI"},"location":"Cairo, Egypt"},
      {"id":12020,"position":{"name":"Civil Engineer"},
       "company":{"title":"Modera"},"location":"Cairo, Egypt"}
    ]}}}
    </script></body></html>
    """

    CONFIG = {
        "json_path": "props.pageProps.jobs",
        "fields": {
            "title": "position.name",
            "company": "company.title",
            "location": "location",
            "id": "id",
        },
        "link_template": "https://www.jobzella.com/job/{id}",
    }

    def test_rows_are_read_from_the_embedded_payload(self) -> None:
        from src.scrapers.extraction import extract_next_data_postings

        rows = extract_next_data_postings(
            self.PAGE,
            self.CONFIG["json_path"],
            self.CONFIG["fields"],
            self.CONFIG["link_template"],
        )
        assert len(rows) == 2
        assert rows[0]["title"] == "AI Engineer"
        assert rows[0]["company"] == "PANNELLI"
        assert rows[0]["url"] == "https://www.jobzella.com/job/12026"

    def test_next_data_feeds_the_collector(self) -> None:
        from src.scrapers.common import _is_relevant_job

        source = make_source(try_json_ld=False, next_data=self.CONFIG)
        result = collect(
            source, "AI Engineer", "Egypt", FakeFetcher(self.PAGE),
            relevance_filter=_is_relevant_job,
        )
        assert result.status == "ok"
        assert result.titles_found == 2
        assert [j["Title"] for j in result.jobs] == ["AI Engineer"]
        assert result.jobs[0]["extraction_method"] == "next_data"

    def test_missing_payload_is_not_an_error(self) -> None:
        from src.scrapers.extraction import extract_next_data_postings

        assert extract_next_data_postings("<html></html>", "a.b", {}) == []

    def test_malformed_payload_is_not_an_error(self) -> None:
        from src.scrapers.extraction import extract_next_data_postings

        page = '<script id="__NEXT_DATA__">{ broken</script>'
        assert extract_next_data_postings(page, "a.b", {}) == []
