# Draw.io MCP 사용 가이드

## 개요
Draw.io MCP 서버를 사용하여 AWS 아키텍처 다이어그램을 생성합니다.

## 중요: 다이어그램 요청 처리 방법

사용자가 "다이어그램 만들어줘", "아키텍처 그려줘" 등의 요청을 하면:

1. **반드시 Draw.io MCP 도구를 사용**해야 합니다
2. Python matplotlib나 다른 그래픽 라이브러리를 사용하지 마세요
3. Draw.io MCP의 `create_new_diagram` 도구를 호출하세요

## 사용 가능한 Draw.io MCP 도구

### 1. start_session
- 새로운 다이어그램 세션 시작
- 브라우저에서 실시간 미리보기 제공

### 2. create_new_diagram
- mxGraphModel XML로 다이어그램 생성
- AWS 아이콘 사용 가능 (shape=mxgraph.aws4.*)

### 3. edit_diagram
- 기존 다이어그램 수정
- ID 기반으로 셀 추가/수정/삭제

### 4. get_diagram
- 현재 다이어그램 XML 조회

### 5. export_diagram
- .drawio 파일로 내보내기

## AWS 아키텍처 다이어그램 생성 예시

```xml
<mxGraphModel>
  <root>
    <mxCell id="0"/>
    <mxCell id="1" parent="0"/>
    
    <!-- VPC -->
    <mxCell id="vpc" value="VPC" 
      style="sketch=0;outlineConnect=0;gradientColor=none;html=1;whiteSpace=wrap;fontSize=12;fontStyle=0;shape=mxgraph.aws4.group;grIcon=mxgraph.aws4.group_vpc;strokeColor=#248814;fillColor=none;verticalAlign=top;align=left;spacingLeft=30;fontColor=#AAB7B8;dashed=0;" 
      vertex="1" parent="1">
      <mxGeometry x="40" y="40" width="720" height="520" as="geometry"/>
    </mxCell>
    
    <!-- EC2 Instance -->
    <mxCell id="ec2" value="EC2 Instance" 
      style="sketch=0;outlineConnect=0;fontColor=#232F3E;gradientColor=none;fillColor=#ED7100;strokeColor=none;dashed=0;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=12;fontStyle=0;aspect=fixed;pointerEvents=1;shape=mxgraph.aws4.ec2_instance;" 
      vertex="1" parent="1">
      <mxGeometry x="320" y="200" width="78" height="78" as="geometry"/>
    </mxCell>
    
    <!-- RDS -->
    <mxCell id="rds" value="RDS Database" 
      style="sketch=0;outlineConnect=0;fontColor=#232F3E;gradientColor=none;fillColor=#C925D1;strokeColor=none;dashed=0;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=12;fontStyle=0;aspect=fixed;pointerEvents=1;shape=mxgraph.aws4.rds_instance;" 
      vertex="1" parent="1">
      <mxGeometry x="560" y="200" width="78" height="78" as="geometry"/>
    </mxCell>
    
    <!-- Connection -->
    <mxCell id="edge1" value="" 
      style="endArrow=classic;html=1;exitX=1;exitY=0.5;entryX=0;entryY=0.5;edgeStyle=orthogonalEdgeStyle;curved=1;" 
      edge="1" parent="1" source="ec2" target="rds">
      <mxGeometry relative="1" as="geometry"/>
    </mxCell>
  </root>
</mxGraphModel>
```

## 주요 AWS 아이콘 Shape 이름

### Compute
- `mxgraph.aws4.ec2_instance` - EC2 인스턴스
- `mxgraph.aws4.lambda_function` - Lambda
- `mxgraph.aws4.ecs_task` - ECS Task
- `mxgraph.aws4.auto_scaling` - Auto Scaling

### Network
- `mxgraph.aws4.application_load_balancer` - ALB
- `mxgraph.aws4.network_load_balancer` - NLB
- `mxgraph.aws4.cloudfront` - CloudFront
- `mxgraph.aws4.route_53` - Route 53
- `mxgraph.aws4.nat_gateway` - NAT Gateway

### Database
- `mxgraph.aws4.rds_instance` - RDS
- `mxgraph.aws4.dynamodb` - DynamoDB
- `mxgraph.aws4.elasticache` - ElastiCache
- `mxgraph.aws4.redshift` - Redshift

### Storage
- `mxgraph.aws4.s3_bucket` - S3
- `mxgraph.aws4.ebs_volume` - EBS
- `mxgraph.aws4.efs` - EFS

### Security
- `mxgraph.aws4.waf` - WAF
- `mxgraph.aws4.shield` - Shield
- `mxgraph.aws4.security_group` - Security Group
- `mxgraph.aws4.role` - IAM Role

### Containers
- `mxgraph.aws4.group_vpc` - VPC 그룹
- `mxgraph.aws4.group_security_group` - Security Group 그룹
- `mxgraph.aws4.group_region` - Region 그룹

## 레이아웃 가이드

- 화면 크기: x=0-800, y=0-600
- 여백: x=40, y=40부터 시작
- 컴포넌트 간격: 150-200px
- 연결선은 orthogonalEdgeStyle 사용
- 각 요소에 고유한 ID 부여

## 다이어그램 요청 처리 플로우

1. 사용자 요청 수신 (예: "3-tier 아키텍처 만들어줘")
2. `create_new_diagram` 도구 호출
3. mxGraphModel XML 생성 (AWS 아이콘 포함)
4. 브라우저에 자동으로 표시됨

## 주의사항

- **절대 Python matplotlib, PIL, 또는 다른 그래픽 라이브러리를 사용하지 마세요**
- **반드시 Draw.io MCP 도구만 사용하세요**
- XML 형식을 정확히 지켜야 합니다
- 모든 셀에는 고유한 ID가 필요합니다
- parent="1"은 최상위 요소를 의미합니다
