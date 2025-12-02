import unittest
import tempfile
import os
from unittest.mock import patch, MagicMock
import sys

# Add the current directory to the path so we can import rss_reader
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rss_reader

class TestRSSReader(unittest.TestCase):

    def setUp(self):
        """Set up test fixtures before each test method."""
        # Create a temporary markdown file for testing
        self.temp_file = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.md')
        self.temp_file.close()

    def tearDown(self):
        """Tear down test fixtures after each test method."""
        if os.path.exists(self.temp_file.name):
            os.unlink(self.temp_file.name)

    def test_extract_feeds_from_markdown_empty_file(self):
        """Test extracting feeds from an empty markdown file."""
        with open(self.temp_file.name, 'w') as f:
            f.write("")

        feeds = rss_reader.extract_feeds_from_markdown(self.temp_file.name)
        self.assertEqual(feeds, [])
        self.assertIsInstance(feeds, list)  # Should return an empty list

    def test_extract_feeds_from_markdown_with_feeds(self):
        """Test extracting feeds from a markdown file with RSS feed entries."""
        markdown_content = """
# RSS Feeds

## Technology
- [Hacker News](https://news.ycombinator.com/rss)
- [TechCrunch](https://techcrunch.com/feed/)

## News
- [BBC News](https://feeds.bbci.co.uk/news/rss.xml)
"""
        with open(self.temp_file.name, 'w') as f:
            f.write(markdown_content)

        feeds = rss_reader.extract_feeds_from_markdown(self.temp_file.name)
        self.assertEqual(len(feeds), 3)
        # feeds now returns (name, url) tuples
        feed_urls = [feed[1] for feed in feeds]
        self.assertIn("https://news.ycombinator.com/rss", feed_urls)
        self.assertIn("https://techcrunch.com/feed/", feed_urls)
        self.assertIn("https://feeds.bbci.co.uk/news/rss.xml", feed_urls)

        # Also check that names are extracted
        feed_names = [feed[0] for feed in feeds]
        self.assertIn("Hacker News", feed_names)
        self.assertIn("TechCrunch", feed_names)
        self.assertIn("BBC News", feed_names)

    @patch('rss_reader.validate_feed_url')
    def test_add_feed_to_markdown_new_feed(self, mock_validate):
        """Test adding a new feed to the markdown file."""
        # Mock the validation to return True
        mock_validate.return_value = (True, "Example Feed")

        # Create a basic markdown file
        with open(self.temp_file.name, 'w') as f:
            f.write("# RSS Feeds\n\n## Uncategorized\n")

        # Add a new feed
        result = rss_reader.add_feed_to_markdown(self.temp_file.name, "https://example.com/rss", "Example Feed")

        # Check that the function returns True for successful addition
        self.assertTrue(result)

        # Read the file back
        with open(self.temp_file.name, 'r') as f:
            content = f.read()

        self.assertIn("Example Feed", content)
        self.assertIn("https://example.com/rss", content)

    @patch('rss_reader.validate_feed_url')
    def test_add_feed_to_markdown_duplicate_prevention(self, mock_validate):
        """Test that duplicate feeds are not added."""
        # Mock the validation to return True
        mock_validate.return_value = (True, "Example Feed")

        # Create a markdown file with an existing feed
        with open(self.temp_file.name, 'w') as f:
            f.write("# RSS Feeds\n\n## Uncategorized\n- [Example Feed](https://example.com/rss)\n")

        # Try to add the same feed again
        result = rss_reader.add_feed_to_markdown(self.temp_file.name, "https://example.com/rss", "Example Feed")

        # Function should return False for duplicate
        self.assertFalse(result)

    @patch('rss_reader.validate_feed_url')
    def test_add_feed_to_markdown_file_creation(self, mock_validate):
        """Test adding a feed to a file that doesn't exist (should create it)."""
        # Mock the validation to return True
        mock_validate.return_value = (True, "Example Feed")

        non_existent_file = "/tmp/test_non_existent_feeds.md"

        if os.path.exists(non_existent_file):
            os.remove(non_existent_file)

        result = rss_reader.add_feed_to_markdown(non_existent_file, "https://example.com/rss", "Example Feed")

        # Function should return True for successful addition
        self.assertTrue(result)

        self.assertTrue(os.path.exists(non_existent_file))

        with open(non_existent_file, 'r') as f:
            content = f.read()

        self.assertIn("Example Feed", content)
        self.assertIn("https://example.com/rss", content)

        # Clean up
        os.remove(non_existent_file)

    @patch('feedparser.parse')
    def test_fetch_feed_entries_success(self, mock_parse):
        """Test fetching entries from a valid RSS feed."""
        mock_feed = MagicMock()
        mock_feed.entries = [
            MagicMock(title="Test Entry 1", published="2023-01-01", link="http://example.com/1", summary="Summary 1"),
            MagicMock(title="Test Entry 2", published="2023-01-02", link="http://example.com/2", summary="Summary 2")
        ]
        mock_feed.feed = MagicMock(title="Test Feed", description="Test Description")
        mock_parse.return_value = mock_feed

        result = rss_reader.fetch_feed_entries("https://example.com/rss")

        self.assertIsNotNone(result)
        self.assertEqual(len(result.entries), 2)
        self.assertEqual(result.feed.title, "Test Feed")

    @patch('feedparser.parse')
    def test_fetch_feed_entries_failure(self, mock_parse):
        """Test handling of feed fetching errors."""
        mock_parse.side_effect = Exception("Network error")

        result = rss_reader.fetch_feed_entries("https://example.com/bad_rss")

        self.assertIsNone(result)


if __name__ == '__main__':
    unittest.main()