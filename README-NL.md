# Dunja Creatief — website en kunstwerkbeheer

Deze applicatie bestaat uit de bestaande website, een eenvoudige beheerpagina en een kleine Flask-API. Nginx serveert de website; Flask beheert de kunstwerken en uploads. SQLite slaat de gegevens op.

De volledige installatiehandleiding (inclusief Podman-commando's, wachtwoordhash en domeinconfiguratie) staat in `README.md`.

- Website: `/`
- Beheerpagina: `/admin/`
- Publieke API: `/api/artworks`
- Uploads: `/uploads/`
- Persistente data: `./data/`
