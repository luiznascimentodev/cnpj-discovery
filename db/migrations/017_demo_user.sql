INSERT INTO users (email, password_hash, name, email_verified_at)
VALUES (
  'demo@cnpjdiscovery.com.br',
  '$argon2id$v=19$m=65536,t=3,p=2$aJuscqa2DH4HTDBdlj1lAg$STBPeBS4tOSPkiGXJGUulWHg9k9yDutAe5e6s//sfcc',
  'Conta Demonstração',
  NOW()
)
ON CONFLICT (email) DO UPDATE SET
  password_hash = EXCLUDED.password_hash,
  name = EXCLUDED.name,
  email_verified_at = COALESCE(users.email_verified_at, EXCLUDED.email_verified_at),
  deleted_at = NULL,
  updated_at = NOW();

UPDATE users
SET deleted_at = NOW(), updated_at = NOW()
WHERE email = 'demo@cnpjdiscovery.local';
