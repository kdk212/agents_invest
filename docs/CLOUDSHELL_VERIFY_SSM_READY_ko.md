# CloudShell에서 SSM 연결 준비 확인

`docs/CLOUDSHELL_COPY_PASTE_SSM_ROLE_COMMAND_ko.md` 명령을 실행한 뒤, EC2에 IAM Role이 제대로 붙었는지 CloudShell에서 확인하는 명령입니다.

현재 대상:

```text
Region: ap-southeast-2
Instance ID: i-08bdbe63b2db7880f
Role: agents-invest-ec2-runtime-role
Instance Profile: agents-invest-ec2-instance-profile
```

## 1. Instance Profile 연결 확인

CloudShell에서 실행합니다.

```bash
aws ec2 describe-instances \
  --region ap-southeast-2 \
  --instance-ids i-08bdbe63b2db7880f \
  --query 'Reservations[0].Instances[0].IamInstanceProfile' \
  --output table
```

정상이라면 `Arn` 또는 `Id`가 보입니다.

비어 있거나 `None`이면 아직 EC2에 Instance Profile이 붙지 않은 것입니다. 이 경우 복붙용 명령을 다시 실행합니다.

## 2. Role에 SSM 정책이 있는지 확인

```bash
aws iam list-attached-role-policies \
  --role-name agents-invest-ec2-runtime-role \
  --query 'AttachedPolicies[*].PolicyName' \
  --output table
```

정상이라면 아래가 보여야 합니다.

```text
AmazonSSMManagedInstanceCore
```

## 3. 운영 inline policy 확인

```bash
aws iam list-role-policies \
  --role-name agents-invest-ec2-runtime-role \
  --output table
```

정상이라면 아래가 보여야 합니다.

```text
agents-invest-runtime-inline-policy
```

이 inline policy는 `/agents-invest/*` Parameter Store 읽기, SecureString 복호화, CloudWatch Logs 쓰기에 필요합니다.

## 4. SSM에 인스턴스가 Online으로 보이는지 확인

재부팅 후 2-5분 기다린 뒤 실행합니다.

```bash
aws ssm describe-instance-information \
  --region ap-southeast-2 \
  --filters Key=InstanceIds,Values=i-08bdbe63b2db7880f \
  --query 'InstanceInformationList[*].[InstanceId,PingStatus,PlatformName,AgentVersion,LastPingDateTime]' \
  --output table
```

정상 목표:

```text
i-08bdbe63b2db7880f | Online
```

목록이 비어 있거나 `Offline`이면 다음 중 하나입니다.

- Role 연결 직후라 아직 반영 대기 중
- EC2 재부팅이 아직 끝나지 않음
- EC2가 SSM 서비스에 네트워크로 접근하지 못함
- SSM Agent가 설치/실행되지 않음

## 5. 그래도 Offline이면 확인할 것

EC2가 public subnet에 있고 outbound가 열려 있는지 확인합니다.

필요 조건:

- EC2에 Public IPv4가 있음
- subnet route table에 Internet Gateway 경로가 있음
- Security Group outbound가 막혀 있지 않음
- Network ACL이 outbound/inbound를 막지 않음

private subnet이면 아래 VPC Endpoint가 필요합니다.

```text
ssm
ssmmessages
ec2messages
```

## 6. Online이 된 뒤

AWS 콘솔에서 접속합니다.

```text
EC2 > Instances > i-08bdbe63b2db7880f > Connect > Session Manager > Connect
```

EC2 안에 들어가면 아래 명령으로 진짜 EC2인지 확인합니다.

```bash
ps -p 1 -o comm=
```

정상 Ubuntu EC2라면 보통 다음이 나옵니다.

```text
systemd
```

그 다음 `docs/NEXT_STEPS_ko.md`의 EC2 설치 단계로 진행합니다.
