"""Hello World Plugin - Example Focomy plugin."""

from core.plugins import Plugin


class HelloWorldPlugin(Plugin):
    """
    Example plugin demonstrating Focomy plugin capabilities.

    Shows how to:
    - Register hooks for content modification
    - Add admin menu items
    - Define settings schema
    - Use plugin templates
    """

    def activate(self):
        """Called when plugin is activated."""
        self.log("Hello World plugin activated!")

        # Register content filter
        self.register_hook(
            "content.before_save",
            self.on_before_save,
            priority=10,
        )

        # Register dashboard widget
        self.register_hook(
            "admin.dashboard",
            self.add_dashboard_widget,
            priority=50,
        )

        # Register admin menu
        self.register_admin_menu(
            title="Hello World",
            path="/admin/plugins/hello-world",
            icon="hand-wave",
        )

        # Register custom route
        self.register_route(
            "/greet",
            "GET",
            self.handle_greet,
        )

    def deactivate(self):
        """Called when plugin is deactivated."""
        self.log("Hello World plugin deactivated!")

    def get_settings_schema(self):
        """Define plugin settings."""
        return [
            {
                "name": "greeting",
                "type": "string",
                "label": "Greeting Text",
                "default": "Hello, World!",
                "description": "The greeting message to display",
            },
            {
                "name": "show_on_dashboard",
                "type": "boolean",
                "label": "Show on Dashboard",
                "default": True,
                "description": "Display greeting widget on admin dashboard",
            },
            {
                "name": "greeting_style",
                "type": "select",
                "label": "Greeting Style",
                "options": ["casual", "formal", "excited"],
                "default": "casual",
            },
        ]

    def on_before_save(self, content: dict) -> dict:
        """
        Filter hook: Modify content before saving.

        Args:
            content: Content data being saved

        Returns:
            Modified content data
        """
        # Add a custom field to track that this content was processed
        if "meta" not in content:
            content["meta"] = {}

        content["meta"]["hello_world_processed"] = True

        return content

    def add_dashboard_widget(self, widgets: list) -> list:
        """
        Filter hook: Add widget to dashboard.

        Args:
            widgets: List of dashboard widgets

        Returns:
            Updated widget list
        """
        settings = self.get_settings()

        if settings.get("show_on_dashboard", True):
            greeting = settings.get("greeting", "Hello, World!")
            style = settings.get("greeting_style", "casual")

            if style == "formal":
                greeting = f"Greetings: {greeting}"
            elif style == "excited":
                greeting = f"{greeting}!!!"

            widgets.append({
                "id": "hello-world",
                "title": "Hello World",
                "content": f"<p>{greeting}</p>",
                "icon": "hand-wave",
                "order": 100,
            })

        return widgets

    async def handle_greet(self, request):
        """
        Route handler: Custom greeting endpoint.

        Args:
            request: HTTP request object

        Returns:
            Response with greeting
        """
        settings = self.get_settings()
        greeting = settings.get("greeting", "Hello, World!")

        return {
            "message": greeting,
            "plugin": self.name,
            "version": self.version,
        }
