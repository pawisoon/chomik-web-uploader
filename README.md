# ChomikUploader Synology

ChomikUploader Synology to wygodny, bezpieczny panel webowy do przesyłania plików z Twojego Synology NAS bezpośrednio na konto Chomikuj.pl.

## Kluczowe funkcje

- Przeglądanie folderów NAS z nawigacją po katalogach
- Wybór i wysyłanie plików bezpośrednio na Chomikuj
- Pliki są widoczne tylko do odczytu, nie są kopiowane ani zapisywane lokalnie
- Bezpieczny dostęp chroniony hasłem
- Działa jako kontener Docker, nie modyfikuje plików na NAS

---

## Instalacja na Synology NAS

### 1. Przygotuj folder z plikami
Wybierz lub utwórz katalog na Synology, np. `/volume1/shared`, który chcesz przeglądać i wysyłać pliki z tego miejsca.

### 2. Stwórz plik `docker-compose.yml`

```yaml
services:
  chomik-uploader:
    image: ghcr.io/pawisoon/chomik-web-uploader:latest
    container_name: chomik-uploader
    ports:
      - "8000:5000"
    environment:
      - PANEL_PASSWORD=twoje_haslo_do_panelu
      - SECRET_KEY=losowy_silny_klucz_min_32_znaki
      - CHOMIK_USERNAME=twoj_login_chomikuj
      - CHOMIK_PASSWORD=twoje_haslo_chomikuj
      - CHOMIK_DEST=/Moje_Uploady
    volumes:
      - /volume1/shared:/app/browse:ro
    restart: unless-stopped
    security_opt:
      - no-new-privileges:true
```

**Uwaga:**
- `SECRET_KEY` powinien być długi i losowy (np. `openssl rand -base64 32`)
- Dane logowania do Chomikuj możesz trzymać także w `.env`

### 3. Uruchom przez Portainer lub SSH

- **Portainer:** Skopiuj treść `docker-compose.yml`, dodaj stack, uzupełnij zmienne środowiskowe, Deploy
- **SSH:**
```bash
cd /ścieżka_do_katalogu/
docker compose up -d
```

### 4. Logowanie

- Wejdź na: `http://twoje-nas:8000`
- Zaloguj się swoim panelem hasłem

### 5. Używanie

- Przeglądaj foldery jak w eksploratorze Windows/NAS
- Kliknij folder żeby wejść do niego
- Zaznacz pliki do wysłania
- Kliknij „Wyślij zaznaczone pliki”
- Status uploadu widoczny na żywo

---

## Bezpieczeństwo
- Panel dostępny tylko po zalogowaniu
- Pliki zawsze w trybie read-only (nie są nadpisywane ani kasowane)
- Folder montowany tylko w trybie odczytu
- Brak zapisywania jakichkolwiek plików w kontenerze

---
## FAQ
- **Błąd portu?** Jeśli 8000 zajęty, zmień na np. "8001:5000" w docker-compose.yml

---

### Autor
pawisoon

PRy mile widziane! Masz problem lub pytania? Otwórz issue na GitHub.

---

MIT License
