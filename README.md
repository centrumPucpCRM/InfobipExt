Local:
git add .
git commit -m "Your commit description"
git push origin main
================================
Desplegado:
git pull origin main
docker build -t infobipext-api .
docker-compose up -d