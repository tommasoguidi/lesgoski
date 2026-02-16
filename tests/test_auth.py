"""Tests for multi-user auth, sharing, broskis, excluded destinations, and ntfy topics."""

from datetime import datetime

import pytest

from lesgoski.database.models import Deal, User, BroskiRequest
from lesgoski.services.matcher import DealMatcher
from lesgoski.webapp.auth import (
    hash_password,
    verify_password,
    generate_ntfy_topic,
    get_broskis,
    get_pending_broski_requests,
)
from tests.conftest import make_flight, make_profile, make_user, make_broski_request


# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------

class TestPasswordHashing:
    def test_hash_and_verify(self):
        hashed = hash_password("mysecretpassword")
        assert hashed != "mysecretpassword"
        assert verify_password("mysecretpassword", hashed) is True

    def test_wrong_password_rejected(self):
        hashed = hash_password("correct")
        assert verify_password("wrong", hashed) is False

    def test_different_hashes_for_same_password(self):
        """bcrypt auto-salts, so two hashes of the same password differ."""
        h1 = hash_password("same")
        h2 = hash_password("same")
        assert h1 != h2
        assert verify_password("same", h1) is True
        assert verify_password("same", h2) is True


# ---------------------------------------------------------------------------
# ntfy topic generation
# ---------------------------------------------------------------------------

class TestNtfyTopicGeneration:
    def test_format(self):
        topic = generate_ntfy_topic()
        parts = topic.split("-")
        assert parts[0] == "lesgoski"
        assert len(parts) == 4  # lesgoski-word1-word2-NN
        assert parts[3].isdigit()
        assert 10 <= int(parts[3]) <= 99

    def test_uniqueness(self):
        topics = {generate_ntfy_topic() for _ in range(50)}
        # With 70*70*90 = 441000 combinations, 50 samples should all be unique
        assert len(topics) == 50


# ---------------------------------------------------------------------------
# User model — excluded destinations
# ---------------------------------------------------------------------------

class TestUserExcludedDestinations:
    def test_default_empty(self, db):
        user = make_user(db)
        assert user.excluded_destinations == []

    def test_set_and_get(self, db):
        user = make_user(db)
        user.excluded_destinations = ["BCN", "GRO"]
        db.flush()
        assert user.excluded_destinations == ["BCN", "GRO"]

    def test_clear(self, db):
        user = make_user(db)
        user.excluded_destinations = ["BCN"]
        db.flush()
        user.excluded_destinations = []
        db.flush()
        assert user.excluded_destinations == []


# ---------------------------------------------------------------------------
# Profile ownership & sharing
# ---------------------------------------------------------------------------

class TestProfileSharing:
    def test_profile_has_owner(self, db):
        user = make_user(db)
        profile = make_profile(db, user=user)
        assert profile.user_id == user.id
        assert profile.user.username == "alice"

    def test_profile_without_owner(self, db):
        """Legacy profiles (pre-migration) have no owner."""
        profile = make_profile(db)
        assert profile.user_id is None

    def test_share_with_viewer(self, db):
        owner = make_user(db, username="owner")
        viewer = make_user(db, username="viewer")
        profile = make_profile(db, user=owner)

        profile.viewers.append(viewer)
        db.flush()

        assert viewer in profile.viewers
        assert owner not in profile.viewers  # owner is not a "viewer"

    def test_unshare(self, db):
        owner = make_user(db, username="owner")
        viewer = make_user(db, username="viewer")
        profile = make_profile(db, user=owner)

        profile.viewers.append(viewer)
        db.flush()
        profile.viewers.remove(viewer)
        db.flush()

        assert viewer not in profile.viewers


# ---------------------------------------------------------------------------
# Matcher — excluded destinations integration
# ---------------------------------------------------------------------------

class TestMatcherExcludedDestinations:
    def test_excluded_destination_filtered_out(self, db, monkeypatch):
        """A deal to an excluded destination should not be matched."""
        monkeypatch.setattr("lesgoski.services.matcher.HOUR_TOLERANCE", 1)
        monkeypatch.setattr("lesgoski.services.matcher.NEARBY_AIRPORT_RADIUS_KM", 0)

        user = make_user(db)
        user.excluded_destinations = ["BCN"]
        db.flush()

        make_flight(db, origin="PSA", destination="BCN",
                    departure_time=datetime(2025, 7, 4, 18, 0), price=30)
        make_flight(db, origin="BCN", destination="PSA",
                    departure_time=datetime(2025, 7, 6, 16, 0), price=30,
                    origin_full="Barcelona Airport, Spain",
                    destination_full="Pisa Airport, Italy")
        profile = make_profile(db, max_price=100, user=user)
        db.flush()

        matcher = DealMatcher(db=db)
        count = matcher.run(profile)
        assert count == 0

    def test_non_excluded_destination_still_matches(self, db, monkeypatch):
        """Destinations not in the exclusion list should still match normally."""
        monkeypatch.setattr("lesgoski.services.matcher.HOUR_TOLERANCE", 1)
        monkeypatch.setattr("lesgoski.services.matcher.NEARBY_AIRPORT_RADIUS_KM", 0)

        user = make_user(db)
        user.excluded_destinations = ["GRO"]  # exclude GRO, not BCN
        db.flush()

        make_flight(db, origin="PSA", destination="BCN",
                    departure_time=datetime(2025, 7, 4, 18, 0), price=30)
        make_flight(db, origin="BCN", destination="PSA",
                    departure_time=datetime(2025, 7, 6, 16, 0), price=30,
                    origin_full="Barcelona Airport, Spain",
                    destination_full="Pisa Airport, Italy")
        profile = make_profile(db, max_price=100, user=user)
        db.flush()

        matcher = DealMatcher(db=db)
        count = matcher.run(profile)
        assert count == 1

    def test_no_user_no_exclusion(self, db, monkeypatch):
        """A profile without a user should match all destinations (legacy mode)."""
        monkeypatch.setattr("lesgoski.services.matcher.HOUR_TOLERANCE", 1)
        monkeypatch.setattr("lesgoski.services.matcher.NEARBY_AIRPORT_RADIUS_KM", 0)

        make_flight(db, origin="PSA", destination="BCN",
                    departure_time=datetime(2025, 7, 4, 18, 0), price=30)
        make_flight(db, origin="BCN", destination="PSA",
                    departure_time=datetime(2025, 7, 6, 16, 0), price=30,
                    origin_full="Barcelona Airport, Spain",
                    destination_full="Pisa Airport, Italy")
        profile = make_profile(db, max_price=100)  # no user
        db.flush()

        matcher = DealMatcher(db=db)
        count = matcher.run(profile)
        assert count == 1


# ---------------------------------------------------------------------------
# Broskis (mutual friends)
# ---------------------------------------------------------------------------

class TestBroskis:
    def test_accepted_request_creates_broskis(self, db):
        alice = make_user(db, username="alice")
        bob = make_user(db, username="bob")
        make_broski_request(db, from_user=alice, to_user=bob, status="accepted")

        assert bob in get_broskis(db, alice)
        assert alice in get_broskis(db, bob)

    def test_pending_request_not_in_broskis(self, db):
        alice = make_user(db, username="alice")
        bob = make_user(db, username="bob")
        make_broski_request(db, from_user=alice, to_user=bob, status="pending")

        assert bob not in get_broskis(db, alice)
        assert alice not in get_broskis(db, bob)

    def test_pending_request_shows_for_receiver(self, db):
        alice = make_user(db, username="alice")
        bob = make_user(db, username="bob")
        req = make_broski_request(db, from_user=alice, to_user=bob, status="pending")

        pending = get_pending_broski_requests(db, bob)
        assert len(pending) == 1
        assert pending[0].id == req.id

        # Sender should NOT see it as pending
        assert get_pending_broski_requests(db, alice) == []

    def test_no_broskis_by_default(self, db):
        alice = make_user(db, username="alice")
        assert get_broskis(db, alice) == []

    def test_broski_symmetry(self, db):
        """If A→B accepted, both see each other as broskis."""
        alice = make_user(db, username="alice")
        bob = make_user(db, username="bob")
        make_broski_request(db, from_user=alice, to_user=bob, status="accepted")

        alice_broskis = get_broskis(db, alice)
        bob_broskis = get_broskis(db, bob)
        assert len(alice_broskis) == 1
        assert len(bob_broskis) == 1
        assert alice_broskis[0].id == bob.id
        assert bob_broskis[0].id == alice.id


# ---------------------------------------------------------------------------
# Favourite profile
# ---------------------------------------------------------------------------

class TestFavouriteProfile:
    def test_default_no_favourite(self, db):
        user = make_user(db)
        assert user.favourite_profile_id is None

    def test_set_favourite(self, db):
        user = make_user(db)
        profile = make_profile(db, user=user)
        user.favourite_profile_id = profile.id
        db.flush()
        assert user.favourite_profile_id == profile.id
        assert user.favourite_profile.name == profile.name

    def test_clear_favourite(self, db):
        user = make_user(db)
        profile = make_profile(db, user=user)
        user.favourite_profile_id = profile.id
        db.flush()
        user.favourite_profile_id = None
        db.flush()
        assert user.favourite_profile_id is None
