# ChomikUploader Synology

ChomikUploader Synology to wygodny, bezpieczny panel webowy do przesyłania plików z Twojego Synology NAS bezpośrednio na konto Chomikuj.pl.

## Kluczowe funkcje

- Przeglądanie folderów NAS z nawigacją po katalogach
- Wybór i wysyłanie pojedynczych plików bezpośrednio na Chomikuj
- Upload całego folderu razem z podfolderami (struktura zachowana po stronie Chomika)
- Postęp uploadu na żywo z paskiem postępu dla każdego pliku
- Przyciski czyszczenia listy statusów (osobno dla ukończonych i osobno dla wszystkich)
- Pliki są widoczne tylko do odczytu, nie są kopiowane ani zapisywane lokalnie
- Bezpieczny dostęp chroniony hasłem
- Działa jako kontener Docker, nie modyfikuje plików na NAS

---

## Zrzuty ekranu

### Logowanie
![Ekran logowania](docs/screenshots/01-login.png)

### Przeglądarka folderów
Każdy folder ma przycisk **⬆ Upload**, który wysyła cały folder razem z zawartością.

![Przeglądarka folderów](docs/screenshots/02-browser.png)

### Status uploadów
Postęp dla każdego pliku z osobna, przyciski czyszczenia listy po prawej stronie.

![Status uploadów](docs/screenshots/03-status.png)

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
- Dane logowania do Chomikuj możesz trzymać w `.env`

### 3. Uruchom przez Portainer lub SSH

- **Portainer:** Skopiuj treść `docker-compose.yml`, dodaj stack, uzupełnij zmienne środowiskowe, Deploy
- **SSH:**
```bash
cd /ścieżka_do_katalogu/
docker compose up -d
```

### 4. Logowanie

- Wejdź na: `http://twoje-nas:8000`
- Zaloguj się hasłem panelu

### 5. Używanie

- Przeglądaj foldery jak w eksploratorze plików, klikaj nazwę żeby wejść do środka
- Zaznacz checkboxami pojedyncze pliki i kliknij **Wyślij zaznaczone pliki**
- Albo kliknij **⬆ Upload** obok folderu, żeby wysłać cały folder razem z podfolderami
- Po stronie Chomika powstanie folder o tej samej nazwie i z tą samą strukturą podfolderów
- Status uploadu z paskiem postępu pojawia się dla każdego pliku z osobna
- **Wyczyść ukończone** chowa pomyślnie przesłane wpisy i zostawia błędy
- **Wyczyść wszystko** czyści cały panel statusów

---

## Bezpieczeństwo
- Panel dostępny tylko po zalogowaniu
- Pliki zawsze w trybie read-only (nie są nadpisywane ani kasowane)
- Folder montowany tylko w trybie odczytu
- Brak zapisywania jakichkolwiek plików w kontenerze

---

## FAQ
- **Błąd portu?** Jeśli 8000 zajęty, zmień na np. "8001:5000" w docker-compose.yml
- **Folder się nie tworzy na Chomiku?** Sprawdź czy `CHOMIK_DEST` nie zawiera znaków specjalnych. Domyślnie `/Moje_Uploady`
- **Upload utknął na 0%?** Po stronie Chomika może być chwilowy problem z autoryzacją, restart kontenera zazwyczaj pomaga

---

### Autor
pawisoon

PRy mile widziane. Masz problem lub pytania? Otwórz issue na GitHub.

---

MIT License
