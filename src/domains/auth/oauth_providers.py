"""
OAuth Provider Abstraction Module

This module provides a pluggable OAuth provider system for social authentication.
Supports Google OAuth with extensibility for GitHub, Apple, and enterprise providers.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from dataclasses import dataclass
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from src._config.settings import settings
from src._config.logger import get_logger
import httpx
from cachetools import TTLCache

logger = get_logger(__name__)


@dataclass
class OAuthUserInfo:
    """Standardized user information from OAuth providers"""
    provider: str
    provider_user_id: str
    email: str
    email_verified: bool
    name: Optional[str] = None
    given_name: Optional[str] = None
    family_name: Optional[str] = None
    picture: Optional[str] = None
    locale: Optional[str] = None


class OAuthProviderError(Exception):
    """Base exception for OAuth provider errors"""
    pass


class TokenVerificationError(OAuthProviderError):
    """Raised when token verification fails"""
    pass


class ProviderNotFoundError(OAuthProviderError):
    """Raised when requested provider is not configured"""
    pass


class OAuthProvider(ABC):
    """Abstract base class for OAuth providers"""
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Return the provider name (e.g., 'google', 'github')"""
        pass
    
    @abstractmethod
    async def verify_id_token(self, token: str) -> OAuthUserInfo:
        """
        Verify an ID token from the provider and extract user information.
        
        Args:
            token: The ID token to verify
            
        Returns:
            OAuthUserInfo containing verified user data
            
        Raises:
            TokenVerificationError: If verification fails
        """
        pass


class GoogleOAuthProvider(OAuthProvider):
    """Google OAuth2 / OpenID Connect provider implementation"""
    
    def __init__(self, client_id: Optional[str] = None):
        self._client_id = client_id or settings.GOOGLE_OAUTH_CLIENT_ID
        # Cache for Google's public keys (reduces latency)
        self._request = google_requests.Request()
    
    @property
    def name(self) -> str:
        return "google"
    
    async def verify_id_token(self, token: str) -> OAuthUserInfo:
        """
        Verify a Google ID token and extract user information.
        
        Google ID token verification includes:
        - Signature validation using Google's public keys
        - Issuer validation (accounts.google.com or https://accounts.google.com)
        - Audience validation (must match our client ID)
        - Expiration validation
        - Email verification status
        
        Args:
            token: Google ID token from client-side sign-in
            
        Returns:
            OAuthUserInfo with verified Google user data
            
        Raises:
            TokenVerificationError: If any verification step fails
        """
        try:
            # Verify the token with Google's library
            # This handles key fetching, caching, and all validation
            idinfo = id_token.verify_oauth2_token(
                token, 
                self._request, 
                self._client_id
            )
            
            # Additional issuer validation
            issuer = idinfo.get('iss', '')
            if issuer not in ['accounts.google.com', 'https://accounts.google.com']:
                raise TokenVerificationError(f"Invalid issuer: {issuer}")
            
            # Check email verification status
            email_verified = idinfo.get('email_verified', False)
            if not email_verified:
                logger.warning(f"Google user {idinfo.get('sub')} has unverified email")
                # We still allow login but flag this for potential restrictions
            
            return OAuthUserInfo(
                provider=self.name,
                provider_user_id=idinfo['sub'],
                email=idinfo['email'],
                email_verified=email_verified,
                name=idinfo.get('name'),
                given_name=idinfo.get('given_name'),
                family_name=idinfo.get('family_name'),
                picture=idinfo.get('picture'),
                locale=idinfo.get('locale')
            )
            
        except ValueError as e:
            logger.error(f"Google ID token verification failed: {e}")
            raise TokenVerificationError(f"Invalid Google ID token: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error verifying Google token: {e}")
            raise TokenVerificationError(f"Token verification failed: {str(e)}")


class GitHubOAuthProvider(OAuthProvider):
    """
    GitHub OAuth2 provider implementation.
    
    Note: GitHub uses OAuth2 (not OpenID Connect), so we exchange
    the authorization code for an access token, then fetch user info.
    """
    
    def __init__(self, client_id: Optional[str] = None, client_secret: Optional[str] = None):
        self._client_id = client_id or getattr(settings, 'GITHUB_OAUTH_CLIENT_ID', None)
        self._client_secret = client_secret or getattr(settings, 'GITHUB_OAUTH_CLIENT_SECRET', None)
    
    @property
    def name(self) -> str:
        return "github"
    
    async def verify_id_token(self, token: str) -> OAuthUserInfo:
        """
        Verify a GitHub access token by fetching user info.
        
        GitHub doesn't use ID tokens like OpenID Connect, so we use
        the access token to fetch user information from their API.
        
        Args:
            token: GitHub access token
            
        Returns:
            OAuthUserInfo with GitHub user data
            
        Raises:
            TokenVerificationError: If verification fails
        """
        try:
            async with httpx.AsyncClient() as client:
                # Fetch user profile
                user_response = await client.get(
                    "https://api.github.com/user",
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Accept": "application/vnd.github+json",
                        "X-GitHub-Api-Version": "2022-11-28"
                    }
                )
                
                if user_response.status_code != 200:
                    raise TokenVerificationError(
                        f"GitHub API returned {user_response.status_code}"
                    )
                
                user_data = user_response.json()
                
                # Fetch user emails (profile email might be private)
                email_response = await client.get(
                    "https://api.github.com/user/emails",
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Accept": "application/vnd.github+json",
                        "X-GitHub-Api-Version": "2022-11-28"
                    }
                )
                
                primary_email = None
                email_verified = False
                
                if email_response.status_code == 200:
                    emails = email_response.json()
                    for email_info in emails:
                        if email_info.get('primary'):
                            primary_email = email_info['email']
                            email_verified = email_info.get('verified', False)
                            break
                
                # Fallback to profile email if available
                if not primary_email:
                    primary_email = user_data.get('email')
                
                if not primary_email:
                    raise TokenVerificationError("Could not retrieve email from GitHub")
                
                return OAuthUserInfo(
                    provider=self.name,
                    provider_user_id=str(user_data['id']),
                    email=primary_email,
                    email_verified=email_verified,
                    name=user_data.get('name'),
                    picture=user_data.get('avatar_url'),
                )
                
        except httpx.RequestError as e:
            logger.error(f"GitHub API request failed: {e}")
            raise TokenVerificationError(f"GitHub API request failed: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error verifying GitHub token: {e}")
            raise TokenVerificationError(f"Token verification failed: {str(e)}")


class OAuthProviderRegistry:
    """
    Registry for OAuth providers.
    
    Provides a centralized way to access configured OAuth providers
    and handles provider lookup by name.
    """
    
    def __init__(self):
        self._providers: Dict[str, OAuthProvider] = {}
        self._initialize_providers()
    
    def _initialize_providers(self):
        """Initialize all configured OAuth providers"""
        
        # Google OAuth (always available if client ID is configured)
        if hasattr(settings, 'GOOGLE_OAUTH_CLIENT_ID') and settings.GOOGLE_OAUTH_CLIENT_ID:
            self._providers['google'] = GoogleOAuthProvider()
            logger.info("Google OAuth provider initialized")
        
        # GitHub OAuth (optional)
        if hasattr(settings, 'GITHUB_OAUTH_CLIENT_ID') and settings.GITHUB_OAUTH_CLIENT_ID:
            self._providers['github'] = GitHubOAuthProvider()
            logger.info("GitHub OAuth provider initialized")
    
    def get_provider(self, name: str) -> OAuthProvider:
        """
        Get a provider by name.
        
        Args:
            name: Provider name (e.g., 'google', 'github')
            
        Returns:
            The OAuth provider instance
            
        Raises:
            ProviderNotFoundError: If provider is not configured
        """
        provider = self._providers.get(name.lower())
        if not provider:
            available = list(self._providers.keys())
            raise ProviderNotFoundError(
                f"Provider '{name}' is not configured. Available providers: {available}"
            )
        return provider
    
    def list_providers(self) -> list[str]:
        """List all available provider names"""
        return list(self._providers.keys())
    
    def is_provider_available(self, name: str) -> bool:
        """Check if a provider is available"""
        return name.lower() in self._providers


# Global singleton registry
oauth_registry = OAuthProviderRegistry()
