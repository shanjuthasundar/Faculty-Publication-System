import unittest

from backend.server import VALID_INDEXING, parse_int_query, parse_publication_payload


class ServerValidationTests(unittest.TestCase):
    def test_parse_publication_payload_accepts_supported_types(self):
        payload = {
            "title": "Faculty Analytics",
            "authors": "Dr. A, Dr. B",
            "venue": "IEEE Access",
            "type": "Conference",
            "conferenceScope": "International Conference",
            "indexing": ["Scopus", "SCI"],
            "submissionDate": "2026-03-20",
            "content": "Publication summary.",
            "impactFactor": 4.5,
            "publisherName": "IEEE",
            "doi": "10.1000/fps-001"
        }

        result = parse_publication_payload(payload)
        self.assertEqual(result["pub_type"], "Conference")
        self.assertEqual(result["conference_scope"], "International Conference")
        self.assertEqual(result["impact_factor"], 4.5)

    def test_parse_publication_payload_rejects_bad_indexing(self):
        payload = {
            "title": "Faculty Analytics",
            "authors": "Dr. A",
            "venue": "IEEE Access",
            "type": "Journal",
            "indexing": ["BadIndex"],
            "submissionDate": "2026-03-20",
            "content": "Publication summary.",
            "impactFactor": 2.0
        }

        with self.assertRaises(Exception):
            parse_publication_payload(payload)

    def test_valid_indexing_set_contains_required_values(self):
        self.assertIn("Scopus", VALID_INDEXING)
        self.assertIn("Non-Scopus", VALID_INDEXING)
        self.assertIn("SCI", VALID_INDEXING)
        self.assertIn("Non-SCI", VALID_INDEXING)

    def test_parse_int_query_clamps_range(self):
        self.assertEqual(parse_int_query("0", 8, 1, 50), 1)
        self.assertEqual(parse_int_query("100", 8, 1, 50), 50)
        self.assertEqual(parse_int_query("abc", 8, 1, 50), 8)


if __name__ == "__main__":
    unittest.main()
