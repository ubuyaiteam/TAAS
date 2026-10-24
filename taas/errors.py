"""Errors with simple messages the user can read."""


class TaasError(Exception):
    """Base error. Its text is safe to show."""


class ConfigError(TaasError):
    """A setting or file is missing or wrong."""


class AuthRequiredError(TaasError):
    """The user must sign in again."""


class NetworkError(TaasError):
    """Could not reach the internet or Google."""


class BloggerError(TaasError):
    """Blogger refused the request."""


class ValidationError(TaasError):
    """The input is not valid."""


class PageReadError(TaasError):
    """A web page could not be read."""


class GeminiError(TaasError):
    """Gemini failed or gave a bad answer."""


class OpenAIError(TaasError):
    """OpenAI failed or gave a bad answer."""


class UpdateError(TaasError):
    """The check for a new version failed."""
