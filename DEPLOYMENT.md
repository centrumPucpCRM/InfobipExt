Local:
------------------------
Cambios de codigo:
------------------------
git add .
git commit -m "Your commit description"
git push origin main
------------------------
Cambios en variables .env
scp -i "infobip.pem" C:\Users\Windows\Downloads\InfobipExt\infobip.db ec2-user@{ip-elastica}:/home/ec2-user/infobip/InfobipExt/
================================================================
Desplegado:
git pull origin main
docker build -t infobipext-api .
docker-compose up -d

