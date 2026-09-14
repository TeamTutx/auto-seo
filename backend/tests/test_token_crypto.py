import pytest

from app.services.token_crypto import TokenDecryptError, decrypt_token, encrypt_token


def test_round_trip():
    ciphertext = encrypt_token("a-real-refresh-token")
    assert ciphertext != "a-real-refresh-token"
    assert decrypt_token(ciphertext) == "a-real-refresh-token"


def test_ciphertext_is_not_plaintext_substring():
    ciphertext = encrypt_token("super-secret-value")
    assert "super-secret-value" not in ciphertext


def test_garbage_input_raises_a_clear_error():
    with pytest.raises(TokenDecryptError):
        decrypt_token("not-a-real-token")
