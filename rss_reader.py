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
from textual.containers import Container, Horizontal, Vertical, ScrollableContainer
from textual.widgets import (
    Header,
    Footer,
    Static,
    ListView,
    ListItem,
    Button,
    Input,
    Label,
    Markdown,
    OptionList
)
from textual import events
from textual.reactive import reactive
from textual.screen import ModalScreen, Screen
from textual.binding import Binding
from textual.widgets.option_list import Option
import feedparser
import re
import os
from datetime import datetime
from colorama import init, Fore, Style, Back
import webbrowser

# Initialize colorama
init(autoreset=True)


def extract_feeds_from_markdown(file_path):
    """
    Extract RSS feed URLs from a markdown file.

    Args:
        file_path (str): Path to the markdown file containing RSS feeds

    Returns:
        list: List of tuples containing (feed_name, feed_url)
    """
    if not os.path.exists(file_path):
        return []

    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Find all markdown links that contain any URLs with names
    # This pattern matches [text](url) format and captures both the text and URL
    pattern = r'\[([^\]]+)\]\((https?://[^\s\)]+)\)'
    all_matches = re.findall(pattern, content)

    # Filter for likely RSS feed URLs
    rss_matches = []
    for name, url in all_matches:
        if any(ext in url.lower() for ext in ['.rss', '.xml', 'feed', 'rss']) or \
           any(pattern in url.lower() for pattern in ['rss', 'feed', 'atom']) or \
           re.search(r'/feed/?$', url) or re.search(r'/rss/?$', url) or \
           any(domain in url for domain in ['feedburner', 'campaign-archive']):
            rss_matches.append((name, url))

    # Return list of (name, url) tuples
    return rss_matches


def validate_feed_url(feed_url):
    """
    Validate if the given URL is a valid RSS feed by attempting to parse it.

    Args:
        feed_url (str): URL to validate

    Returns:
        tuple: (is_valid, feed_title) where is_valid is boolean and feed_title is the feed's title if valid
    """
    try:
        feed = feedparser.parse(feed_url)
        # Check if parsing was successful and contains feed data
        if feed and hasattr(feed, 'feed') and hasattr(feed.feed, 'title'):
            return True, feed.feed.title
        return False, None
    except Exception:
        return False, None


def add_feed_to_markdown(file_path, feed_url, feed_name=None):
    """
    Add a new RSS feed to the markdown file.

    Args:
        file_path (str): Path to the markdown file
        feed_url (str): URL of the RSS feed to add
        feed_name (str): Name for the feed (optional)
    """
    # Validate the feed URL first
    is_valid, feed_title = validate_feed_url(feed_url)
    if not is_valid:
        return False  # Not a valid RSS feed

    # If no name provided, use the feed's title from the feed data, or fallback to domain
    if not feed_name:
        if feed_title and feed_title != "Unknown Feed":
            feed_name = feed_title
        else:
            # Extract domain from URL as fallback
            feed_name = feed_url.split('//')[1].split('/')[0]

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


class FeedListItem(ListItem):
    """Widget to display a single feed in the sidebar."""

    def __init__(self, title, feed_url):
        self.feed_title = title
        self.feed_url = feed_url
        super().__init__()

    def compose(self) -> ComposeResult:
        yield Static(self.feed_title, classes="feed-sidebar-title")

    def on_click(self) -> None:
        self.app.select_feed(self.feed_title, self.feed_url)


class ArticleListItem(ListItem):
    """Widget to display a single article in the articles list."""

    def __init__(self, title, published, link, summary, feed_title):
        self.title = title
        self.published = published
        self.link = link
        self.summary = summary
        self.feed_title = feed_title
        super().__init__()

    def compose(self) -> ComposeResult:
        yield Static(f"[bold]{self.title}[/bold]", classes="article-list-title")
        yield Static(f"[italic]{self.published}[/italic]", classes="article-list-published")

    def on_click(self) -> None:
        self.app.select_article(self.title, self.published, self.link, self.summary, self.feed_title)


class AddFeedModal(ModalScreen):
    """Modal dialog for adding a new feed."""

    BINDINGS = [
        ("escape", "dismiss_modal", "Cancel"),
    ]

    def compose(self) -> ComposeResult:
        with Vertical(id="add-feed-modal"):
            yield Label("Add New RSS Feed", classes="modal-title")
            yield Label("Feed URL:", classes="input-label")
            yield Input(placeholder="https://example.com/rss", id="feed-url-input")
            yield Label("Feed Name (optional):", classes="input-label")
            yield Input(placeholder="e.g., Example News", id="feed-name-input")
            with Horizontal(classes="button-container"):
                yield Button("Add Feed", variant="success", id="add-button")
                yield Button("Cancel", variant="error", id="cancel-button")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle input submission."""
        if event.input.id == "feed-url-input":
            # Move focus to feed name input
            self.query_one("#feed-name-input").focus()
        elif event.input.id == "feed-name-input":
            # Trigger the add button click
            self.query_one("#add-button").press()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "add-button":
            url_input = self.query_one("#feed-url-input", Input)
            name_input = self.query_one("#feed-name-input", Input)

            feed_url = url_input.value
            feed_name = name_input.value

            if feed_url:
                # Validate the feed URL first
                is_valid, extracted_name = validate_feed_url(feed_url)
                if not is_valid:
                    self.app.notify("Invalid RSS feed URL. Please provide a valid RSS feed.", severity="error")
                    return

                # If no name provided, use the extracted name from the feed
                if not feed_name and extracted_name and extracted_name != "Unknown Feed":
                    feed_name = extracted_name

                # Notify the main app to add the feed
                success = self.app.add_feed(feed_url, feed_name)
                if success:
                    self.app.notify("Feed added successfully!", timeout=3)
                    self.dismiss(True)
                else:
                    self.app.notify("Feed already exists!", timeout=3, severity="warning")
            else:
                self.app.notify("Please enter a feed URL", severity="error")
        elif event.button.id == "cancel-button":
            self.dismiss(False)

    def action_dismiss_modal(self) -> None:
        """Action to dismiss the modal when ESC is pressed."""
        self.dismiss(False)


class MainGridScreen(Screen):
    """Main application screen with grid layout: sidebar, articles list, and article detail."""

    def __init__(self):
        super().__init__()
        self.all_feeds = {}
        self.selected_feed_title = None
        self.selected_feed_url = None
        self.loading_feeds = False  # Flag to prevent multiple concurrent loads

    def compose(self) -> ComposeResult:
        """Create child widgets for the main screen."""
        yield Header()

        with Horizontal(id="main-grid"):
            # Left column: feed list sidebar
            with Vertical(id="feeds-sidebar"):
                yield Static("RSS Feeds", classes="sidebar-title")
                yield ListView(id="feeds-list")

            # Right side: articles list and article detail
            with Vertical(id="articles-section"):
                yield Static("Articles", classes="articles-section-title")
                with Horizontal(id="articles-content"):
                    with Vertical(id="articles-list-container"):
                        yield ListView(id="articles-list")
                    with ScrollableContainer(id="article-detail"):
                        yield Static("Select an article to view its content", id="article-placeholder", classes="article-placeholder")

        yield Footer()

    def on_mount(self) -> None:
        """Called when the screen is mounted."""
        # Load the UI immediately, then fetch feeds in the background
        self.load_feeds_async()

    def load_feeds_async(self):
        """Load feeds from markdown file and update UI asynchronously."""
        if self.loading_feeds:
            return  # Prevent multiple simultaneous loads

        self.loading_feeds = True

        # Show loading message in the feeds list
        feeds_list = self.query_one("#feeds-list", ListView)
        loading_item = ListItem(Static("Loading feeds...", classes="loading-text"))
        feeds_list.clear()
        feeds_list.append(loading_item)

        # Load feeds from markdown file - returns (name, url) tuples
        feed_data = extract_feeds_from_markdown('feeds.md')

        # Use asyncio with thread executor to run in background and update UI
        import asyncio
        from concurrent.futures import ThreadPoolExecutor
        import threading

        def fetch_feeds_in_thread():
            """Function to fetch feeds in a background thread."""
            feeds_data = {}
            for feed_name, feed_url in feed_data:
                try:
                    feed_data_obj = fetch_feed_entries(feed_url)
                    if feed_data_obj:
                        # Use the name from the markdown file, but fallback to feed title if needed
                        feed_title = getattr(feed_data_obj.feed, 'title', feed_name)
                        if feed_title == "Unknown Feed":
                            feed_title = feed_name
                        feeds_data[feed_url] = {
                            'title': feed_title,
                            'data': feed_data_obj,
                            'display_name': feed_name  # Store the name from markdown
                        }
                    else:
                        # If we couldn't fetch the feed, use the display name from markdown
                        feeds_data[feed_url] = {
                            'title': feed_name,
                            'data': None,
                            'display_name': feed_name
                        }
                except Exception:
                    # If there's an error, use the display name from markdown
                    feeds_data[feed_url] = {
                        'title': feed_name,
                        'data': None,
                        'display_name': feed_name
                    }

            # Schedule UI update on the main thread
            self.app.call_later(self._update_feeds_ui, feeds_data)

        # Run the function in a separate thread
        thread = threading.Thread(target=fetch_feeds_in_thread, daemon=True)
        thread.start()

    def _on_feeds_loaded(self, result):
        """Handle the result of the feed loading worker."""
        # Update UI in the main thread with the result
        self._update_feeds_ui(result.value)

    def _update_feeds_ui(self, feeds_data):
        """Update the feeds UI with loaded data."""
        # Update UI in the main thread
        self.all_feeds = feeds_data

        # Update the UI with the feed list
        feeds_list = self.query_one("#feeds-list", ListView)
        feeds_list.clear()
        for feed_url, feed_info in self.all_feeds.items():
            feed_item = FeedListItem(feed_info['title'], feed_url)
            feeds_list.append(feed_item)

        self.loading_feeds = False

    def show_articles_for_feed(self, feed_url):
        """Display articles for the selected feed."""
        if feed_url in self.all_feeds:
            feed_data = self.all_feeds[feed_url]['data']
            articles_list = self.query_one("#articles-list", ListView)
            articles_list.clear()

            # Show loading message while populating articles
            articles_list.append(ListItem(Static("Loading articles...", classes="loading-text")))

            # Clear and repopulate with actual articles
            articles_list.clear()
            for entry in feed_data.entries:
                title = getattr(entry, 'title', 'No Title')
                published = getattr(entry, 'published', 'Unknown Date')
                link = getattr(entry, 'link', 'No Link')
                summary = getattr(entry, 'summary', 'No Summary')
                # Clean up HTML from summary
                clean_summary = re.sub('<[^<]+?>', '', summary)

                article_item = ArticleListItem(title, published, link, clean_summary, self.all_feeds[feed_url]['title'])
                articles_list.append(article_item)

    def show_article_detail(self, title, published, link, summary, feed_title):
        """Display the selected article in the detail view."""
        detail_container = self.query_one("#article-detail", ScrollableContainer)

        # Clear previous content
        detail_container.query('*').remove()

        # Add new article content
        detail_container.mount(Static(f"[bold]{title}[/bold]", classes="selected-article-title"))
        detail_container.mount(Static(f"Feed: {feed_title}", classes="selected-article-feed"))
        detail_container.mount(Static(f"Published: {published}", classes="selected-article-published"))
        detail_container.mount(Static(f"Link: {link}", classes="selected-article-link"))
        detail_container.mount(Static("\n" + summary, classes="selected-article-summary"))


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
    current_view = reactive("main")

    def __init__(self):
        super().__init__()
        self.main_screen = MainGridScreen()

    def on_mount(self) -> None:
        """Called when the app is mounted."""
        self.title = "Textual RSS Reader"
        self.push_screen(self.main_screen)

    def load_feeds(self):
        """Load feeds on the current screen."""
        if hasattr(self.screen, 'load_feeds'):
            self.screen.load_feeds()

    def select_feed(self, feed_title: str, feed_url: str):
        """Handle feed selection from the sidebar."""
        self.main_screen.selected_feed_title = feed_title
        self.main_screen.selected_feed_url = feed_url
        self.main_screen.show_articles_for_feed(feed_url)

    def select_article(self, title: str, published: str, link: str, summary: str, feed_title: str):
        """Handle article selection from the articles list."""
        self.main_screen.show_article_detail(title, published, link, summary, feed_title)

    def add_feed(self, feed_url: str, feed_name: str = None) -> bool:
        """Add a new feed to the markdown file."""
        success = add_feed_to_markdown('feeds.md', feed_url, feed_name)
        if success:
            self.notify("Feed added successfully!", timeout=3)
            # Reload the feeds display
            self.load_feeds()
        else:
            self.notify("Feed already exists!", timeout=3, severity="warning")
        return success

    def action_add_feed(self) -> None:
        """Action to add a new feed."""
        add_modal = AddFeedModal()
        self.push_screen(add_modal)

    def action_refresh(self) -> None:
        """Action to refresh the feeds."""
        self.notify("Refreshing feeds...", timeout=2)
        self.load_feeds()

    def action_show_main(self) -> None:
        """Action to show the main feeds view."""
        # If we're on the main screen, just refresh
        if isinstance(self.screen, MainGridScreen):
            self.load_feeds()


if __name__ == "__main__":
    app = TextualRSSReaderApp()
    app.run()