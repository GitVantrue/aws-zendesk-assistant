# Draw.io 다이어그램 생성 가이드

## ⚠️ 절대 금지: MCP 도구 호출 금지

**CRITICAL**: 다음 도구들을 절대 호출하지 마세요:
- `start_session` - 절대 사용 금지
- `create_new_diagram` - 절대 사용 금지
- `edit_diagram` - 절대 사용 금지
- `export_diagram` - 절대 사용 금지
- `get_diagram` - 절대 사용 금지
- 기타 모든 Draw.io MCP 도구 - 절대 사용 금지

**이유**: 서버 환경에서는 브라우저가 없어 실패합니다.

## 올바른 방법: XML 텍스트만 생성

사용자가 "다이어그램 만들어줘", "아키텍처 그려줘" 등의 요청을 하면:

1. **MCP 도구를 호출하지 말고**
2. **mxGraphModel XML 텍스트만 생성하여 응답하세요**
3. Python matplotlib나 다른 그래픽 라이브러리도 사용하지 마세요

클라이언트 브라우저에서 Draw.io iframe으로 렌더링합니다.

## 🔄 다이어그램 수정 모드

사용자가 기존 다이어그램을 수정하려는 경우:

1. **현재 다이어그램 XML이 제공됩니다** (프롬프트에 포함됨)
2. **사용자가 요청한 변경사항만 적용하세요**
3. **수정된 전체 XML을 생성하여 응답하세요**

### 수정 예시

사용자 요청: "Lambda 함수 추가해줘"

1. 현재 XML에서 기존 컴포넌트 확인
2. Lambda 함수 노드 추가
3. 필요한 연결선(edge) 추가
4. 전체 XML 반환

**중요**: 
- 기존 컴포넌트의 ID는 유지하세요
- 새 컴포넌트는 고유한 ID를 부여하세요
- 레이아웃이 겹치지 않도록 좌표를 조정하세요

## ⚠️ 중요: XML 구조

**반드시 이 구조로 생성하세요** (diagram 태그 필수):

```xml
<?xml version="1.0" encoding="UTF-8"?>
<mxfile host="embed.diagrams.net" modified="2024-01-01T00:00:00.000Z" agent="5.0" version="22.0.0">
  <diagram name="AWS Architecture" id="aws-diagram">
    <mxGraphModel dx="1422" dy="794" grid="1" gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" pageWidth="850" pageHeight="1100">
      <root>
        <mxCell id="0"/>
        <mxCell id="1" parent="0"/>
        <!-- 여기에 컴포넌트들 추가 -->
      </root>
    </mxGraphModel>
  </diagram>
</mxfile>
```

**XML 구조 규칙**:
- `<mxfile>` → `<diagram>` → `<mxGraphModel>` → `<root>` 순서
- `</mxGraphModel>` 다음에 반드시 `</diagram>` 
- `</diagram>` 다음에 `</mxfile>`로 닫기

## AWS 아키텍처 다이어그램 예시

3-tier 아키텍처 예시:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<mxfile host="embed.diagrams.net" modified="2024-01-01T00:00:00.000Z" agent="5.0" version="22.0.0">
  <diagram name="3-Tier Architecture" id="3tier">
    <mxGraphModel dx="1422" dy="794" grid="1" gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" pageWidth="850" pageHeight="1100">
      <root>
        <mxCell id="0"/>
        <mxCell id="1" parent="0"/>
        
        <!-- VPC -->
        <mxCell id="vpc" value="VPC" 
          style="sketch=0;outlineConnect=0;gradientColor=none;html=1;whiteSpace=wrap;fontSize=12;fontStyle=0;shape=mxgraph.aws4.group;grIcon=mxgraph.aws4.group_vpc;strokeColor=#248814;fillColor=none;verticalAlign=top;align=left;spacingLeft=30;fontColor=#AAB7B8;dashed=0;" 
          vertex="1" parent="1">
          <mxGeometry x="40" y="40" width="720" height="520" as="geometry"/>
        </mxCell>
        
        <!-- ALB -->
        <mxCell id="alb" value="Application Load Balancer" 
          style="sketch=0;outlineConnect=0;fontColor=#232F3E;gradientColor=none;fillColor=#8C4FFF;strokeColor=none;dashed=0;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=12;fontStyle=0;aspect=fixed;pointerEvents=1;shape=mxgraph.aws4.application_load_balancer;" 
          vertex="1" parent="1">
          <mxGeometry x="360" y="100" width="78" height="78" as="geometry"/>
        </mxCell>
        
        <!-- EC2 -->
        <mxCell id="ec2" value="EC2 Instance" 
          style="sketch=0;outlineConnect=0;fontColor=#232F3E;gradientColor=none;fillColor=#ED7100;strokeColor=none;dashed=0;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=12;fontStyle=0;aspect=fixed;pointerEvents=1;shape=mxgraph.aws4.ec2_instance;" 
          vertex="1" parent="1">
          <mxGeometry x="360" y="250" width="78" height="78" as="geometry"/>
        </mxCell>
        
        <!-- RDS -->
        <mxCell id="rds" value="RDS Database" 
          style="sketch=0;outlineConnect=0;fontColor=#232F3E;gradientColor=none;fillColor=#C925D1;strokeColor=none;dashed=0;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=12;fontStyle=0;aspect=fixed;pointerEvents=1;shape=mxgraph.aws4.rds_instance;" 
          vertex="1" parent="1">
          <mxGeometry x="360" y="400" width="78" height="78" as="geometry"/>
        </mxCell>
        
        <!-- Connections -->
        <mxCell id="edge1" value="" 
          style="endArrow=classic;html=1;exitX=0.5;exitY=1;entryX=0.5;entryY=0;edgeStyle=orthogonalEdgeStyle;curved=1;" 
          edge="1" parent="1" source="alb" target="ec2">
          <mxGeometry relative="1" as="geometry"/>
        </mxCell>
        
        <mxCell id="edge2" value="" 
          style="endArrow=classic;html=1;exitX=0.5;exitY=1;entryX=0.5;entryY=0;edgeStyle=orthogonalEdgeStyle;curved=1;" 
          edge="1" parent="1" source="ec2" target="rds">
          <mxGeometry relative="1" as="geometry"/>
        </mxCell>
      </root>
    </mxGraphModel>
  </diagram>
</mxfile>
```

## 주요 AWS 아이콘 Shape 이름

### Compute
- `mxgraph.aws4.ec2_instance` - EC2
- `mxgraph.aws4.lambda_function` - Lambda
- `mxgraph.aws4.ecs_task` - ECS
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

## 응답 형식

반드시 다음 형식으로 응답하세요:

```
AWS 아키텍처 다이어그램을 생성했습니다.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<mxfile host="embed.diagrams.net" modified="2024-01-01T00:00:00.000Z" agent="5.0" version="22.0.0">
  <diagram name="AWS Architecture" id="aws-diagram">
    <mxGraphModel dx="1422" dy="794" grid="1" gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" pageWidth="850" pageHeight="1100">
      <root>
        <mxCell id="0"/>
        <mxCell id="1" parent="0"/>
        <!-- 컴포넌트들 -->
      </root>
    </mxGraphModel>
  </diagram>
</mxfile>
```

클라이언트 브라우저에서 렌더링됩니다.
```

## 주의사항

- **절대 Draw.io MCP 도구를 호출하지 마세요**
- **절대 파일을 생성하지 마세요**
- **반드시 XML 텍스트만 응답하세요**
- `<diagram>` 태그는 반드시 필요합니다
- XML 구조를 정확히 지켜야 합니다
- 모든 셀에는 고유한 ID가 필요합니다
- parent="1"은 최상위 요소를 의미합니다
- AWS 아이콘은 shape=mxgraph.aws4.* 형식을 사용합니다
