# generate_login_key(name) (slugified name + secrets.token_urlsafe suffix, shown once), hash_key()/verify_key() 
# (argon2 hashing so the plaintext key is never stored), create_access_token()/decode_access_token() 
# (JWT encode/decode with expiry claim)