import unittest

from src.job_filter import filter_jobs


class FilterJobsBalancedTests(unittest.TestCase):
    def test_keeps_explicit_and_unknown_but_excludes_conflict(self):
        jobs = [
            {"Title": "Junior AI Engineer"},
            {"Title": "AI Engineer"},
            {"Title": "Senior AI Engineer"},
        ]

        result = filter_jobs(jobs, "Junior")

        self.assertEqual(len(result), 2)
        self.assertEqual([job["seniority_match"] for job in result], ["explicit", "unknown"])

    def test_any_level_marks_all_as_explicit(self):
        jobs = [{"Title": "AI Engineer"}, {"Title": "Senior AI Engineer"}]

        result = filter_jobs(jobs, "Any level")

        self.assertEqual(len(result), 2)
        self.assertTrue(all(job["seniority_match"] == "explicit" for job in result))

    def test_unknown_level_does_not_drop_jobs(self):
        jobs = [{"Title": "Data Scientist"}]

        result = filter_jobs(jobs, "Unspecified")

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["seniority_match"], "unknown")


if __name__ == "__main__":
    unittest.main()
