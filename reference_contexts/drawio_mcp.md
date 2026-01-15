# Draw.io 다이어그램 생성 가이드

## 개요
AWS 아키텍처 다이어그램을 mxGraphModel XML 형식으로 생성합니다.

## ⚠️ 중요: 도구 호출 금지

사용자가 "다이어그램 만들어줘", "아키텍처 그려줘" 등의 요청을 하면:

1. **Draw.io MCP 도구를 호출하지 마세요** (start_session, create_new_diagram 등)
2. **대신 mxGraphModel XML 텍스트만 생성하여 응답하세요**
3. Python matplotlib나 다른 그래픽 라이브러리도 사용하지 마세요

## 왜 도구를 호출하지 않나요?

- 서버 환경에서는 브라우저가 없어 `start_session`이 실패합니다
- 대신 클라이언트 브라우저에서 Draw.io iframe으로 렌더링합니다
- 서버는 XML만 생성하여 전달하면 됩니다

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
2. 요청 분석 및 필요한 AWS 컴포넌트 결정
3. mxGraphModel XML 생성 (아래 예시 참고)
4. **XML 텍스트를 코드 블록으로 응답**
5. 클라이언트가 브라우저에서 렌더링

## 응답 형식

반드시 다음 형식으로 응답하세요:

```
AWS 아키텍처 다이어그램을 생성했습니다.

```xml
<mxGraphModel>
  <root>
    <mxCell id="0"/>
    <mxCell id="1" parent="0"/>
    <!-- 컴포넌트들 -->
  </root>
</mxGraphModel>
```

클라이언트 브라우저에서 렌더링됩니다.
```

## 주의사항

- **절대 Draw.io MCP 도구를 호출하지 마세요** (start_session, create_new_diagram 등)
- **절대 Python matplotlib, PIL, 또는 다른 그래픽 라이브러리를 사용하지 마세요**
- **반드시 mxGraphModel XML 텍스트만 생성하여 응답하세요**
- XML 형식을 정확히 지켜야 합니다
- 모든 셀에는 고유한 ID가 필요합니다
- parent="1"은 최상위 요소를 의미합니다
- AWS 아이콘은 shape=mxgraph.aws4.* 형식을 사용합니다
