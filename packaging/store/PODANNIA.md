# Подання «Накази ШКОЛА» в Microsoft Store

Акаунт Partner Center – той самий, що для «Сканер ШКОЛА» (UAIT).

1. Partner Center → Apps and games → New product → MSIX or PWA app → зарезервувати назву «Накази ШКОЛА».
2. Product management → Product identity: `Package/Identity/Name` → `packaging/store_identity.json` (IdentityName).
   Publisher і PublisherDisplayName вже як у «Сканера» (той самий акаунт) – звірити.
3. Зібрати: `build.bat` (тести, EXE, підпис, інсталятор), далі `python packaging/make_msix.py` → `dist\NakazyShkola.msix`.
4. Submission: Pricing – Free, ринок Україна; Properties – Education / Instructional tools, політика конфіденційності – текст із LISTING.md;
   Age ratings – IARC 3+; Packages – `dist\NakazyShkola.msix`; Store listing uk-UA – з LISTING.md, знімки 01–03 з цієї теки;
   Submission options – обґрунтування runFullTrust і примітки для сертифікації з LISTING.md.
5. Submit for certification – лише на окреме «так» користувача.

Оновлення: підняти `__version__` у `nakazy/__init__.py` і `Version` у `store_identity.json` (формат 0.1.1.0).
