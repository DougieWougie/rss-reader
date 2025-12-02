#!/usr/bin/env python3
"""
Textual-based RSS Feed Reader

A rich terminal user interface for reading RSS feeds using the Textual library.
"""

import rich
from rich.text import Text
from rich.panel import Panel
from rich.table import Table
from rich.console import Console

import asyncio
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Header, Footer, Static, ListView, ListItem, Button
from textual import events
from textual.reactive import reactive
import feedparser
import re
import os
from datetime import datetime
from colorama import init, Fore, Style, Back

# Initialize colorama
init(autoreset=True)


def extract_feeds_from_markdown(file_path):
    """
    Extract RSS feed URLs from a markdown file.
    
    Args:
        file_path (str): Path to the markdown file containing RSS feeds
        
    Returns:
        list: List of RSS feed URLs
    """
    if not os.path.exists(file_path):
        return []
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Find all markdown links that likely contain RSS feed URLs
    # This pattern matches [text](url) format
    pattern = r'\[.*?\]\((https?://[^\s\)]+)\)'
    matches = re.findall(pattern, content)
    
    return matches


def add_feed_to_markdown(file_path, feed_url, feed_name=None):
    """
    Add a new RSS feed to the markdown file.
    
    Args:
        file_path (str): Path to the markdown file
        feed_url (str): URL of the RSS feed to add
        feed_name (str): Name for the feed (optional)
    """
    # If no name provided, try to get it from the URL
    if not feed_name:
        feed_name = feed_url.split('//')[1].split('/')[0]  # domain name
    
    # Ensure the file has content structure
    if not os.path.exists(file_path):
        content = "# RSS Feeds\n\nThis file contains the list of RSS feeds for the terminal RSS reader.\n\n## Uncategorized\n"
    else:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # If there's no "Uncategorized" section, add one
        if "## Uncategorized" not in content and "# RSS Feeds" in content:
            content += "\n## Uncategorized\n"
        elif "# RSS Feeds" not in content:
            content = "# RSS Feeds\n\nThis file contains the list of RSS feeds for the terminal RSS reader.\n\n## Uncategorized\n" + content
    
    # Add the new feed to the last section
    new_feed_line = f"- [{feed_name}]({feed_url})\n"
    
    # Check if this feed URL already exists in the content
    if f"({feed_url})" in content:
        return False  # Feed already exists
    
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
        f.write(new_feed_line)
    
    return True  # Feed successfully added


def fetch_feed_entries(feed_url):
    """
    Fetch entries from a single RSS feed.
    
    Args:
        feed_url (str): URL of the RSS feed
        
    Returns:
        dict: Parsed feed data
    """
    try:
        feed = feedparser.parse(feed_url)
        return feed
    except Exception as e:
        print(f"{Fore.RED}Error fetching feed {feed_url}: {e}{Style.RESET_ALL}")
        return None


class FeedItem(Static):
    """Widget to display a single feed item."""
    
    def __init__(self, title, published, link, summary, feed_title):
        self.title = title
        self.published = published
        self.link = link
        self.summary = summary
        self.feed_title = feed_title
        super().__init__()
    
    def compose(self) -> ComposeResult:
        yield Static(f"[bold]{self.title}[/bold]", classes="title")
        yield Static(f"[italic]{self.published}[/italic]", classes="published")
        yield Static(self.summary[:200] + "..." if len(self.summary) > 200 else self.summary, classes="summary")
    
    def on_click(self) -> None:
        self.app.open_article(self.link)


class FeedList(Container):
    """Container for a list of feeds."""

    def __init__(self, feed_title, entries):
        self.feed_title = feed_title
        self.entries = entries
        super().__init__()

    def compose(self) -> ComposeResult:
        yield Static(f"[bold]{self.feed_title}[/bold]", classes="feed-title")
        for entry in self.entries:
            title = getattr(entry, 'title', 'No Title')
            published = getattr(entry, 'published', 'Unknown Date')
            link = getattr(entry, 'link', 'No Link')
            summary = getattr(entry, 'summary', 'No Summary')
            # Clean up HTML from summary
            import re
            clean_summary = re.sub('<[^<]+?>', '', summary)

            feed_item = FeedItem(title, published, link, clean_summary, self.feed_title)
            yield feed_item


class ArticleView(Static):
    """Widget to display a single article."""
    
    def __init__(self, feed_title, title, published, link, summary):
        self.feed_title = feed_title
        self.title = title
        self.published = published
        self.link = link
        self.summary = summary
        super().__init__()
    
    def compose(self) -> ComposeResult:
        yield Static(f"[bold]{self.title}[/bold]", classes="article-title")
        yield Static(f"Feed: {self.feed_title}", classes="article-feed")
        yield Static(f"Published: {self.published}", classes="article-published")
        yield Static(f"Link: {self.link}", classes="article-link")
        yield Static("\n" + self.summary, classes="article-summary")


class MainView(Container):
    """Main application view showing all feeds."""

    def __init__(self):
        super().__init__()
        self.all_feeds = []
        self.all_feed_data = []

        # Load feeds from markdown file
        feeds = extract_feeds_from_markdown('feeds.md')
        self.all_feeds = feeds

        # Fetch feed data
        for feed_url in feeds:
            feed_data = fetch_feed_entries(feed_url)
            if feed_data:
                self.all_feed_data.append(feed_data)

    def compose(self) -> ComposeResult:
        # Create feed lists directly as child widgets
        for feed_data in self.all_feed_data:
            feed_title = getattr(feed_data.feed, 'title', 'Unknown Feed')
            entries = feed_data.entries[:5]  # Show first 5 entries
            feed_list = FeedList(feed_title, entries)
            yield feed_list


class TextualRSSReaderApp(App):
    """Textual-based RSS Reader Application."""
    
    CSS_PATH = "rss_reader.tcss"
    
    BINDINGS = [
        ("q", "quit", "Quit"),
        ("a", "add_feed", "Add Feed"),
        ("r", "refresh", "Refresh"),
        ("f", "show_main", "Feeds"),
    ]
    
    # Reactive state
    current_view = reactive("main")  # Can be "main", "article", or "add"
    current_article = reactive(None)
    feeds_list = reactive([])
    
    def __init__(self):
        super().__init__()
        self.main_view = MainView()
        self.article_view = None
        
    def compose(self) -> ComposeResult:
        """Create child widgets for the app."""
        yield Header()
        yield self.main_view
        yield Footer()
    
    def on_mount(self) -> None:
        """Called when the app is mounted."""
        self.title = "Textual RSS Reader"
        
        # Load feeds initially
        self.load_feeds()
    
    def load_feeds(self):
        """Load feeds from markdown file and update UI."""
        feeds = extract_feeds_from_markdown('feeds.md')
        self.feeds_list = feeds
        
        # Update the main view
        self.main_view.remove()
        self.main_view = MainView()
        self.mount(self.main_view, before=self.query_one(Footer))
    
    def open_article(self, link: str) -> None:
        """Open an article view."""
        # For now, just show a placeholder since we don't have the full article data
        self.notify(f"Opening article in browser: {link}")
        import webbrowser
        webbrowser.open(link)
    
    def action_add_feed(self) -> None:
        """Action to add a new feed."""
        # For now, we'll just add a sample feed for demonstration
        # In a full implementation, we'd have a dialog to enter feed info
        success = add_feed_to_markdown('feeds.md', 'https://example.com/newfeed.xml', 'New Example Feed')
        if success:
            self.notify("Feed added successfully!")
            self.load_feeds()  # Reload the feeds display
        else:
            self.notify("Feed already exists!")
    
    def action_refresh(self) -> None:
        """Action to refresh the feeds."""
        self.notify("Refreshing feeds...")
        self.load_feeds()
    
    def action_show_main(self) -> None:
        """Action to show the main feeds view."""
        self.notify("Showing feeds...")
        # This is already the main view, so just refresh
        self.load_feeds()


# Default CSS for the Textual app
DEFAULT_CSS = """
Screen {
    background: $surface;
    color: $text;
}

Header {
    background: $primary;
    color: $text;
    text-align: center;
    height: 2;
}

Footer {
    background: $primary;
    color: $text;
    text-align: center;
    height: 2;
}

.feed-title {
    margin: 1 0;
    text-style: bold;
    color: $accent;
}

.entries-container {
    margin-left: 2;
}

.title {
    margin: 1 0 0 0;
    text-style: bold;
}

.published {
    color: $success;
    margin: 0 0 1 0;
}

.summary {
    margin: 0 0 2 0;
    color: $text-muted;
}
"""


if __name__ == "__main__":
    # Write the CSS to a file if it doesn't exist
    css_path = "rss_reader.tcss"
    if not os.path.exists(css_path):
        with open(css_path, 'w') as f:
            f.write(DEFAULT_CSS)
    
    app = TextualRSSReaderApp()
    app.run()