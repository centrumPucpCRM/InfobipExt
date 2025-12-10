------------------
Cambios de codigo:
------------------
Local:
git add .
git commit -m "Adaptando el json de entrada a lo que puede mandar OSC"
git push origin main
================================================================
Desplegado:
git pull origin main
docker build -t infobipext-api .
docker-compose up -d
================================================================
---------------------------------------
Comandos de sincronizacion de archivos:
---------------------------------------
Comando para subir el .env:
scp -i "infobip.pem" C:\Users\Windows\Downloads\InfobipExt\.env ec2-user@{ip-elastica}:/home/ec2-user/infobip/InfobipExt/
--------------------------------------
Comando para obtner los datos de la bd:
scp -i "infobip.pem" ec2-user@{ip-elastica}:/home/ec2-user/infobip/InfobipExt/.env C:\Users\Windows\Downloads\InfobipExt\
