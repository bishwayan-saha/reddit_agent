import logging
import os

import praw
import requests
from dotenv import load_dotenv
from google.adk.agents.llm_agent import LlmAgent
from google.adk.artifacts import InMemoryArtifactService
from google.adk.memory.in_memory_memory_service import InMemoryMemoryService
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_reddit_news(subreddit: str, limit: int) -> dict[str, list[str]]:
    """
    Fetches top post titles from a specified subreddit using the Reddit API.

    Args:
        subreddit: The name of the subreddit to fetch news from.
        limit: The maximum number of top posts to fetch.

    Returns:
        A dictionary with the subreddit name as key and a list of
        post titles as value. Returns an error message if credentials are
        missing, the subreddit is invalid, or an API error occurs.
    """

    client_id = os.getenv("REDDIT_CLIENT_ID")
    client_secret = os.getenv("REDDIT_CLIENT_SECRET")
    user_agent = os.getenv("REDDIT_USER_AGENT")

    try:
        reddit = praw.Reddit(
            client_id=client_id, client_secret=client_secret, user_agent=user_agent
        )
        sub_reddit = reddit.subreddit(subreddit)
        posts = list(sub_reddit.hot(limit=limit))
        titles = [post.title for post in posts]
        return {subreddit: titles}
    except Exception as e:
        logger.errorint(f"--- Tool error: Unexpected error for r/{subreddit}: {e} ---")
        return {
            subreddit: [
                f"An unexpected error occurred while fetching from r/{subreddit}."
            ]
        }


class RedditAgent:

    SUPPORTED_CONTENT_TYPES = ["text", "text/plain"]

    def __init__(self):
        """
        Initialize the RedditAgent.
        Sets up session handling, memory and runner to execute task
        """
        self._credentials = requests.get(
            "https://interop-ae-chat.azurewebsites.net/credentials"
        ).json()
        for creds in self._credentials["data"]:
            os.environ[creds] = self._credentials["data"].get(creds)
        load_dotenv()

        self._agent = self._build_agent()
        self._user_id = "remote_reddit_agent"
        ## Runner is used to manage the agent and its environment
        self._runner = Runner(
            app_name=self._agent.name,
            agent=self._agent,
            artifact_service=InMemoryArtifactService(),  # retreive files/ docs/ artifacts
            session_service=InMemorySessionService(),  # keeps track of conversation by managing sessions
            memory_service=InMemoryMemoryService(),  # Optional: remembers past messages
        )

    def _build_agent(self) -> LlmAgent:
        """Creates and returns an LlmAgent instance"""
        return LlmAgent(
            model="gemini-2.0-flash",
            name="reddit_agent",
            description="""A specialized Reddit agent that searches for relevant posts on a given subreddit.""",
            instruction="""
                You are the Reddit News Scout. Your primary task is to fetch new posts from a given subreddit.
                1. **Identify Intent:** Determine if the user is asking for any subreddit  news or related topics.
                2. **Determine Subreddit:** Identify which subreddit(s) to check. If none specified, prompt the user to enter'.
                3. **Synthesize Output:** Take the exact list of titles returned by the tool.
                4. **Format Response:** Present the information as a concise, bulleted list. Clearly state which subreddit(s) the information came from. 
                        If the tool indicates an error or an unknown subreddit, report that message directly.
                5. **MUST CALL TOOL:** You **MUST** call the `get_reddit_news` tool with the identified subreddit(s).
                        DO NOT generate random summaries without calling the tool first.""",
            tools=[get_reddit_news],
        )

    def invoke(self, query: str, session_id: str) -> str:
        """
        Receives a user query about subreddit news and returns a response
        Args:
            query (str): The query to be processed
            session_id (str): The session ID for context of grouping messages
        Returns:
            str: The response (subreddit posts) from the agent
        """
        session = self._runner.session_service.get_session(
            app_name=self._agent.name, user_id=self._user_id, session_id=session_id
        )

        if not session:
            session = self._runner.session_service.create_session(
                app_name=self._agent.name, user_id=self._user_id, session_id=session_id
            )

        ## Formatting user message in way the model can understand
        content = types.Content(role="user", parts=[types.Part.from_text(text=query)])

        ## Run the aget using Runner and get the response events
        events = list(
            self._runner.run(
                user_id=self._user_id, session_id=session_id, new_message=content
            )
        )

        ## Fallback response if no events are returned
        if not events or not events[-1].content or not events[-1].content.parts:
            return "No response from agent"

        ## Extract the responses text from all events and join them
        response_text = "\n".join(
            [part.text for part in events[-1].content.parts if part.text]
        )

        return response_text
