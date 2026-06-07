"""
Test database operations.
"""

import pytest
import asyncio
from datetime import datetime

from database import DatabaseManager, Software, User
from models.software import SoftwareRepository
from models.user import UserRepository
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker


# Test database URL
TEST_DATABASE_URL = "sqlite+aiosqlite:///test_database.db"


@pytest.fixture
async def db_manager():
    """Create test database manager."""
    manager = DatabaseManager(TEST_DATABASE_URL)
    await manager.initialize()
    yield manager
    await manager.close()
    
    # Clean up test database
    import os
    if os.path.exists("test_database.db"):
        os.remove("test_database.db")


@pytest.fixture
async def session(db_manager):
    """Get test database session."""
    async for sess in db_manager.get_session():
        yield sess


@pytest.mark.asyncio
async def test_add_software(session: AsyncSession):
    """Test adding software."""
    software = await SoftwareRepository.add_software(
        session=session,
        name="Test Software",
        message_id=12345,
        channel_id="@test_channel",
        description="A test software",
        version="1.0.0",
        file_type="exe",
        file_size=50.5,
    )
    
    assert software.id is not None
    assert software.name == "Test Software"
    assert software.version == "1.0.0"
    assert software.file_size == 50.5


@pytest.mark.asyncio
async def test_get_software(session: AsyncSession):
    """Test getting software by ID."""
    # Add software first
    software = await SoftwareRepository.add_software(
        session=session,
        name="Get Test",
        message_id=54321,
        channel_id="@test_channel",
    )
    
    # Retrieve it
    retrieved = await SoftwareRepository.get_by_id(session, software.id)
    
    assert retrieved is not None
    assert retrieved.name == "Get Test"
    assert retrieved.id == software.id


@pytest.mark.asyncio
async def test_search_software(session: AsyncSession):
    """Test searching software."""
    # Add test data
    await SoftwareRepository.add_software(
        session=session,
        name="Chrome Browser",
        message_id=111,
        channel_id="@test_channel",
        description="Web browser",
    )
    await SoftwareRepository.add_software(
        session=session,
        name="Firefox Browser",
        message_id=222,
        channel_id="@test_channel",
        description="Another web browser",
    )
    await SoftwareRepository.add_software(
        session=session,
        name="Visual Studio Code",
        message_id=333,
        channel_id="@test_channel",
        description="Code editor",
    )
    
    # Search for browsers
    results, total = await SoftwareRepository.search_software(
        session=session,
        query="browser",
    )
    
    assert total == 2
    assert len(results) == 2
    assert any(s.name == "Chrome Browser" for s in results)
    assert any(s.name == "Firefox Browser" for s in results)


@pytest.mark.asyncio
async def test_update_software(session: AsyncSession):
    """Test updating software."""
    # Add software
    software = await SoftwareRepository.add_software(
        session=session,
        name="Update Test",
        message_id=777,
        channel_id="@test_channel",
        version="1.0",
    )
    
    # Update it
    await SoftwareRepository.update_software(
        session=session,
        software_id=software.id,
        version="2.0",
        description="Updated description",
    )
    
    # Verify update
    updated = await SoftwareRepository.get_by_id(session, software.id)
    assert updated.version == "2.0"
    assert updated.description == "Updated description"


@pytest.mark.asyncio
async def test_delete_software(session: AsyncSession):
    """Test deleting software."""
    # Add software
    software = await SoftwareRepository.add_software(
        session=session,
        name="Delete Test",
        message_id=888,
        channel_id="@test_channel",
    )
    
    # Soft delete
    await SoftwareRepository.delete_software(session, software.id, soft_delete=True)
    
    # Verify it's deactivated
    deleted = await SoftwareRepository.get_by_id(session, software.id)
    assert deleted is None  # Should not be found (is_active=False)


@pytest.mark.asyncio
async def test_user_operations(session: AsyncSession):
    """Test user operations."""
    # Create user
    user = await UserRepository.get_or_create_user(
        session=session,
        user_id=123456,
        username="testuser",
        first_name="Test",
        last_name="User",
    )
    
    assert user.id == 123456
    assert user.username == "testuser"
    
    # Get user again
    same_user = await UserRepository.get_or_create_user(
        session=session,
        user_id=123456,
    )
    assert same_user.id == user.id
    
    # Block user
    await UserRepository.block_user(session, 123456)
    blocked_user = await UserRepository.get_user_by_id(session, 123456)
    assert blocked_user.is_blocked == True
    
    # Unblock user
    await UserRepository.unblock_user(session, 123456)
    unblocked = await UserRepository.get_user_by_id(session, 123456)
    assert unblocked.is_blocked == False


@pytest.mark.asyncio
async def test_favorites(session: AsyncSession):
    """Test favorites operations."""
    # Create user and software
    user = await UserRepository.get_or_create_user(
        session=session,
        user_id=99999,
        username="favuser",
    )
    software = await SoftwareRepository.add_software(
        session=session,
        name="Favorite Software",
        message_id=555,
        channel_id="@test_channel",
    )
    
    # Add favorite
    result = await UserRepository.add_favorite(session, user.id, software.id)
    assert result == True
    
    # Duplicate favorite
    result = await UserRepository.add_favorite(session, user.id, software.id)
    assert result == False
    
    # Get favorites
    favorites, total = await UserRepository.get_user_favorites(session, user.id)
    assert total == 1
    assert favorites[0]["software_id"] == software.id
    
    # Remove favorite
    await UserRepository.remove_favorite(session, user.id, software.id)
    favorites, total = await UserRepository.get_user_favorites(session, user.id)
    assert total == 0


@pytest.mark.asyncio
async def test_ratings(session: AsyncSession):
    """Test rating operations."""
    # Create user and software
    user = await UserRepository.get_or_create_user(
        session=session,
        user_id=77777,
        username="rater",
    )
    software = await SoftwareRepository.add_software(
        session=session,
        name="Rated Software",
        message_id=666,
        channel_id="@test_channel",
    )
    
    # Add rating
    result = await UserRepository.rate_software(
        session=session,
        user_id=user.id,
        software_id=software.id,
        rating=4,
        review="Good software!",
    )
    assert result == True
    
    # Get user rating
    user_rating = await UserRepository.get_user_rating(
        session, user.id, software.id
    )
    assert user_rating is not None
    assert user_rating["rating"] == 4
    assert user_rating["review"] == "Good software!"
    
    # Update rating
    await UserRepository.rate_software(
        session=session,
        user_id=user.id,
        software_id=software.id,
        rating=5,
    )
    
    # Check updated rating
    updated = await UserRepository.get_user_rating(
        session, user.id, software.id
    )
    assert updated["rating"] == 5


@pytest.mark.asyncio
async def test_invalid_rating(session: AsyncSession):
    """Test invalid rating values."""
    user = await UserRepository.get_or_create_user(
        session=session,
        user_id=88888,
    )
    software = await SoftwareRepository.add_software(
        session=session,
        name="Invalid Rating Test",
        message_id=999,
        channel_id="@test_channel",
    )
    
    # Invalid rating (too high)
    result = await UserRepository.rate_software(
        session=session,
        user_id=user.id,
        software_id=software.id,
        rating=10,
    )
    assert result == False
    
    # Invalid rating (too low)
    result = await UserRepository.rate_software(
        session=session,
        user_id=user.id,
        software_id=software.id,
        rating=0,
    )
    assert result == False


# Run tests
if __name__ == "__main__":
    pytest.main([__file__, "-v"])