"""Regression tests. Each test names the item it locks in."""

from __future__ import annotations

import pytest

from job_radar.collectors.html_collector import HtmlSearchCollector
from job_radar.config.sources import CardSelectors, FetcherKind, SourceConfig
from job_radar.domain.models import ExtractionMethod, JobPosting
from job_radar.extraction.jsonld import extract_job_postings
from job_radar.extraction.normalize import absolutise, clean_text, strip_query
from job_radar.fetching.fetcher import FetchError


class FakeFetcher:
    """Satisfies the PageFetcher protocol without a browser."""

    def __init__(self, html: str | None = None, error: str | None = None) -> None:
        self._html = html
        self._error = error

    def fetch(self, url: str) -> str:
        if self._error:
            raise FetchError(self._error)
        assert self._html is not None
        return self._html


def make_source(**overrides: object) -> SourceConfig:
    defaults: dict[str, object] = {
        "name": "testsite",
        "fetcher": FetcherKind.STATIC,
        "base_url": "https://example.com",
        "search_url_template": (
            "https://example.com/search?q={keyword}&loc={location}&start={start}"
        ),
        "try_json_ld": True,
        "min_expected_results": 1,
        "selectors": CardSelectors(
            card=["li.job"],
            title=["h3"],
            title_link=["a.job-link"],
            company=["span.company"],
            location=["span.loc"],
        ),
    }
    defaults.update(overrides)
    return SourceConfig.model_validate(defaults)


# --------------------------------------------------------------------------
# Item 6 -- names are never mutilated
# --------------------------------------------------------------------------
def test_hyphenated_company_names_survive() -> None:
    assert clean_text("E-finance") == "E-finance"
    assert clean_text("Al-Ahly Momkn") == "Al-Ahly Momkn"


def test_whitespace_is_collapsed_not_removed() -> None:
    assert clean_text("  AI   \n Engineer\t") == "AI Engineer"
    assert clean_text("Vodafone\u00a0Egypt") == "Vodafone Egypt"


# --------------------------------------------------------------------------
# Item 2 -- blank means None, so `if not company` works
# --------------------------------------------------------------------------
def test_blank_text_becomes_none() -> None:
    assert clean_text("   ") is None
    assert clean_text("") is None
    assert clean_text("\u200b") is None


def test_blank_company_field_normalises_to_none() -> None:
    job = JobPosting(
        platform="testsite",
        title="AI Engineer",
        company="   ",
        extraction_method=ExtractionMethod.CSS,
    )
    assert job.company is None
    assert not job.is_complete


# --------------------------------------------------------------------------
# Item 4 -- URL encoding
# --------------------------------------------------------------------------
def test_keyword_is_percent_encoded() -> None:
    url = make_source().build_url("AI Engineer & ML", "Cairo, Egypt")
    assert "AI+Engineer+%26+ML" in url
    assert "Cairo%2C+Egypt" in url


def test_arabic_keyword_is_encoded() -> None:
    url = make_source().build_url("مهندس ذكاء اصطناعي", "مصر")
    assert " " not in url
    assert "%D9" in url


# --------------------------------------------------------------------------
# Item 8 -- JSON-LD path
# --------------------------------------------------------------------------
JSON_LD_PAGE = """
<html><head>
<script type="application/ld+json">
{"@context":"https://schema.org","@graph":[
 {"@type":"WebSite","name":"ignore me"},
 {"@type":"JobPosting","title":"Senior AI Engineer",
  "datePosted":"2026-09-02T08:00:00Z",
  "hiringOrganization":{"@type":"Organization","name":"E-finance"},
  "jobLocation":{"@type":"Place","address":{"addressLocality":"Cairo","addressCountry":"EG"}},
  "url":"https://example.com/jobs/1"}]}
</script>
<script type="application/ld+json">{ this is broken json </script>
</head><body></body></html>
"""


def test_json_ld_is_extracted_and_broken_blocks_are_skipped() -> None:
    postings = extract_job_postings(JSON_LD_PAGE)
    assert len(postings) == 1
    assert postings[0]["title"] == "Senior AI Engineer"
    assert postings[0]["company"] == "E-finance"
    assert postings[0]["location"] == "Cairo, EG"
    assert postings[0]["posted_at"] is not None


def test_json_ld_preferred_over_css() -> None:
    result = HtmlSearchCollector(make_source(), FakeFetcher(JSON_LD_PAGE)).collect(
        "AI Engineer", "Egypt"
    )
    assert result.status == "ok"
    assert result.jobs[0].extraction_method is ExtractionMethod.JSON_LD


# --------------------------------------------------------------------------
# Item 10 -- unknown company stays unknown, never guessed
# --------------------------------------------------------------------------
NO_COMPANY_PAGE = """
<ul>
  <li class="job">
    <h3>AI Engineer</h3>
    <a class="job-link" href="/jobs/42">view</a>
    <span class="loc">Cairo, Egypt</span>
    <span class="posted">2 days ago</span>
    <span>Full Time</span>
  </li>
</ul>
"""


def test_missing_company_is_none_not_a_wrong_guess() -> None:
    source = make_source(try_json_ld=False)
    result = HtmlSearchCollector(source, FakeFetcher(NO_COMPANY_PAGE)).collect(
        "AI Engineer", "Egypt"
    )
    job = result.jobs[0]
    assert job.company is None
    assert job.company not in ("Cairo, Egypt", "2 days ago", "Full Time")


# --------------------------------------------------------------------------
# Item 3 -- one bad card must not kill the rest of the page
# --------------------------------------------------------------------------
def test_one_broken_card_does_not_abort_the_page(monkeypatch: pytest.MonkeyPatch) -> None:
    page = """
    <ul>
      <li class="job"><h3>Job A</h3><a class="job-link" href="/a">x</a></li>
      <li class="job"><h3>BOOM</h3></li>
      <li class="job"><h3>Job C</h3><a class="job-link" href="/c">x</a></li>
    </ul>
    """
    from job_radar.extraction import css as css_module

    original = css_module.extract_card_fields

    def exploding(card, selectors):  # type: ignore[no-untyped-def]
        fields = original(card, selectors)
        if fields["title"] == "BOOM":
            raise ValueError("simulated parse failure")
        return fields

    monkeypatch.setattr(css_module, "extract_card_fields", exploding)

    result = HtmlSearchCollector(
        make_source(try_json_ld=False), FakeFetcher(page)
    ).collect("AI Engineer", "Egypt")

    assert [j.title for j in result.jobs] == ["Job A", "Job C"]
    assert result.card_errors == 1
    assert result.status == "degraded"


# --------------------------------------------------------------------------
# Item 1 -- zero results is never reported as success
# --------------------------------------------------------------------------
def test_zero_results_is_not_success() -> None:
    result = HtmlSearchCollector(
        make_source(try_json_ld=False), FakeFetcher("<html><body></body></html>")
    ).collect("AI Engineer", "Egypt")
    assert result.status == "empty"
    assert not result.is_healthy


def test_fetch_failure_is_recorded_not_swallowed() -> None:
    result = HtmlSearchCollector(
        make_source(), FakeFetcher(error="timeout")
    ).collect("AI Engineer", "Egypt")
    assert result.status == "failed"
    assert result.fatal_error is not None


def test_below_threshold_is_degraded() -> None:
    page = '<ul><li class="job"><h3>Only One</h3></li></ul>'
    result = HtmlSearchCollector(
        make_source(try_json_ld=False, min_expected_results=5), FakeFetcher(page)
    ).collect("AI Engineer", "Egypt")
    assert result.status == "degraded"


# --------------------------------------------------------------------------
# Item 22 -- links resolve correctly and tracking params are dropped
# --------------------------------------------------------------------------
def test_relative_links_are_absolutised() -> None:
    assert absolutise("/jobs/42", "https://example.com") == "https://example.com/jobs/42"
    assert absolutise(None, "https://example.com") is None
    assert absolutise("javascript:void(0)", "https://example.com") is None


def test_tracking_params_are_stripped_when_configured() -> None:
    assert (
        strip_query("https://x.com/jobs/view/1?refId=abc&trk=xyz")
        == "https://x.com/jobs/view/1"
    )


def test_no_job_link_selector_match_yields_none_url() -> None:
    page = '<ul><li class="job"><h3>AI Engineer</h3><a href="/company/acme">Acme</a></li></ul>'
    result = HtmlSearchCollector(
        make_source(try_json_ld=False), FakeFetcher(page)
    ).collect("AI Engineer", "Egypt")
    # The company link must NOT be picked up as the job link.
    assert result.jobs[0].url is None


# --------------------------------------------------------------------------
# Item 11 -- a new source is config only
# --------------------------------------------------------------------------
def test_new_source_needs_no_new_code() -> None:
    bayt_like = make_source(
        name="bayt",
        selectors=CardSelectors(
            card=["div.card"], title=["h2"], title_link=["h2 a"], company=["p.co"]
        ),
    )
    page = '<div class="card"><h2><a href="/j/9">ML Engineer</a></h2><p class="co">Bayt Co</p></div>'
    result = HtmlSearchCollector(bayt_like, FakeFetcher(page)).collect("ML", "Egypt")
    assert result.jobs[0].company == "Bayt Co"
    assert result.jobs[0].platform == "bayt"
