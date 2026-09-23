from datetime import date, timedelta

import pytest

from app import validators as v


class TestPhone:
    def test_normalizes_formatting(self):
        assert v.validate_phone("(305) 555-0142") == "3055550142"

    def test_strips_leading_country_code(self):
        assert v.validate_phone("+1 305 555 0142") == "3055550142"

    def test_rejects_three_digits(self):
        with pytest.raises(ValueError):
            v.validate_phone("911")

    def test_rejects_area_code_starting_zero_or_one(self):
        with pytest.raises(ValueError):
            v.validate_phone("0055550142")
        with pytest.raises(ValueError):
            v.validate_phone("1055550142")


class TestDob:
    def test_accepts_spec_format(self):
        assert v.validate_dob("04/12/1985") == date(1985, 4, 12)

    def test_accepts_iso(self):
        assert v.validate_dob("1985-04-12") == date(1985, 4, 12)

    def test_rejects_future(self):
        future = (date.today() + timedelta(days=30)).strftime("%m/%d/%Y")
        with pytest.raises(ValueError, match="future"):
            v.validate_dob(future)

    def test_rejects_gibberish(self):
        with pytest.raises(ValueError):
            v.validate_dob("not a date")

    def test_rejects_over_120_years(self):
        with pytest.raises(ValueError):
            v.validate_dob("01/01/1850")


class TestStateZipSexName:
    def test_state_abbrev_and_full_name(self):
        assert v.validate_state("fl") == "FL"
        assert v.validate_state("New York") == "NY"

    def test_state_invalid(self):
        with pytest.raises(ValueError):
            v.validate_state("ZZ")

    def test_zip_five_and_plus_four(self):
        assert v.validate_zip("33101") == "33101"
        assert v.validate_zip("33101-1234") == "33101-1234"
        with pytest.raises(ValueError):
            v.validate_zip("331")

    def test_sex_aliases(self):
        assert v.validate_sex("male") == "Male"
        assert v.validate_sex("prefer not to say") == "Decline to Answer"
        with pytest.raises(ValueError):
            v.validate_sex("unicorn")

    def test_name_allows_hyphen_apostrophe(self):
        assert v.validate_name("O'Brien-Smith") == "O'Brien-Smith"
        with pytest.raises(ValueError):
            v.validate_name("R2-D2!")
        with pytest.raises(ValueError):
            v.validate_name("x" * 51)
