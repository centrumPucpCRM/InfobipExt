------------------
Cambios de codigo:
------------------
Local:
git add .
git commit -m "Agregando notas a la conversacion de cartera y de jp"
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
Comando para obtener los datos de la bd (pull):
scp -i "infobip.pem" ec2-user@{ip-elastica}:/home/ec2-user/infobip/InfobipExt/infobip.db C:\Users\Windows\Downloads\InfobipExt\

scp -i "infobip.pem" ec2-user@44.212.240.212:/home/ec2-user/infobip/InfobipExt/infobip.db C:\Users\Windows\Downloads\InfobipExt\

Comando para subir la bd desde local al servidor (push):
    scp -i "infobip.pem" C:\Users\Windows\Downloads\InfobipExt\infobip.db ec2-user@44.212.240.212:/home/ec2-user/infobip/InfobipExt/

