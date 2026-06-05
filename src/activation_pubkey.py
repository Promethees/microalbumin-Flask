"""Embedded RSA public key for verifying permanent activation tokens.

The online server signs hardware-locked permanent activation tokens (RS256) with
the matching private key (its ACTIVATION_PRIVATE_KEY env var). The desktop client
ships only this public half, so it can verify a token's signature offline — proving
the token was issued by our server and has not been altered — without ever being
able to mint one itself.

Keep this in sync with keys/activation_public.pem. Rotating the key pair
invalidates every existing permanent token (users must re-activate), so rotate
only on compromise. See keys/README.md.
"""

ACTIVATION_PUBLIC_KEY_PEM = b"""-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAjPWLYhrnhZG+CwlvuZ+V
i4sow8RG1j6IEIGGtPgR1OLgDQ/OQ3QBhwRN0mGa/6CAHir4V91P1e9HQE1DHGFX
PQFh4s1r9kL3i59KDuV058f2QSJ89vjBsRfTlQaao8mHRA2g2sPPkwi0q3FLXlgN
pZa45oztEf8PgmCXcOSfebtK3Er8zdU186SClwLSNug6OJEqasXPOvK5PdvRz1Ob
2th0lxbNI97JP7ff6Nd1VnHry9IVvXmwtHqof6ftPros4EpM+IZ6g8CGsJ1RDb1/
OrAu+FRZ9dBYWq2V/JJovII9G6rhu94s+rk5CucdjDO8POUnOzA70pZlI59t4oqi
6wIDAQAB
-----END PUBLIC KEY-----
"""
