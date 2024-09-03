FROM --platform=linux/amd64 python:3.9-bullseye

RUN sed -i "s@http://deb.debian.org@http://mirrors.aliyun.com@g" /etc/apt/sources.list
RUN sed -i "s@http://security.debian.org@http://mirrors.aliyun.com@g" /etc/apt/sources.list
RUN ln -fs /usr/share/zoneinfo/Asia/Shanghai /etc/localtime

# RUN apt-get update && apt-get install -y language-pack-zh-hans
RUN pip3 install openai==1.42.0 langchain==0.2.14 langchain-openai==0.1.22 langchain-anthropic==0.1.23 \
  connectai ca-lark-oauth ca-lark-sdk ca-lark-webhook ca-lark-websocket ca-dingtalk-sdk ca-dingtalk-websocket --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn

WORKDIR /server

ADD ./.env /server/.env
ADD ./config.py /server/config.py
ADD ./feishu.py /server/feishu.py
ADD ./server.py /server/server.py

CMD ["python3", "/server/server.py"]

