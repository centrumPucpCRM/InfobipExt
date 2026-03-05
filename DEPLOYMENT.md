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
free -h
--------------------------------------
Comando para obtener los datos de la bd (pull):
scp -i "infobip.pem" ec2-user@xx:/home/ec2-user/infobip/InfobipExt/infobip.db C:\Users\Windows\Downloads\InfobipExt\

scp -i "infobip.pem" ec2-user@44.212.240.212:/home/ec2-user/infobip/InfobipExt/infobip.db C:\Users\Windows\Downloads\InfobipExt\

Comando para subir la bd desde local al servidor (push):
    scp -i "infobip.pem" C:\Users\Windows\Downloads\InfobipExt\infobip.db ec2-user@44.212.240.212:/home/ec2-user/infobip/InfobipExt/




#ahora el archivo es muy grande asi que hacer:
ssh -i "infobip.pem" ec2-user@44.212.240.212 "gzip -c /home/ec2-user/infobip/InfobipExt/infobip.db > /tmp/infobip.db.gz"

scp -i "infobip.pem" ec2-user@44.212.240.212:/tmp/infobip.db.gz C:\Users\Windows\Downloads\InfobipExt\