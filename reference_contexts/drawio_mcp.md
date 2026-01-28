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

**표준 규칙을 적용한 3-tier 아키텍처 예시:**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<mxfile host="embed.diagrams.net" modified="2024-01-01T00:00:00.000Z" agent="5.0" version="22.0.0">
  <diagram name="3-Tier Architecture" id="3tier">
    <mxGraphModel dx="1422" dy="794" grid="1" gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" pageWidth="850" pageHeight="1100">
      <root>
        <mxCell id="0"/>
        <mxCell id="1" parent="0"/>
        
        <!-- VPC Container (부모 먼저) -->
        <mxCell id="vpc" value="VPC (10.0.0.0/16)" 
          style="sketch=0;outlineConnect=0;gradientColor=none;html=1;whiteSpace=wrap;fontSize=12;fontStyle=0;shape=mxgraph.aws4.group;grIcon=mxgraph.aws4.group_vpc;strokeColor=#248814;fillColor=none;verticalAlign=top;align=left;spacingLeft=30;fontColor=#AAB7B8;dashed=0;container=1;" 
          vertex="1" parent="1">
          <mxGeometry x="40" y="40" width="720" height="520" as="geometry"/>
        </mxCell>
        
        <!-- Public Subnet (VPC 내부, 상대 좌표) -->
        <mxCell id="public-subnet" value="Public Subnet" 
          style="sketch=0;outlineConnect=0;gradientColor=none;html=1;whiteSpace=wrap;fontSize=11;fontStyle=0;shape=mxgraph.aws4.group;grIcon=mxgraph.aws4.group_subnet;strokeColor=#248814;fillColor=#E9F3E6;verticalAlign=top;align=left;spacingLeft=30;fontColor=#248814;dashed=0;container=1;" 
          vertex="1" parent="vpc">
          <mxGeometry x="20" y="40" width="680" height="140" as="geometry"/>
        </mxCell>
        
        <!-- ALB (Public Subnet 내부) -->
        <mxCell id="alb" value="Application&#xa;Load Balancer" 
          style="sketch=0;outlineConnect=0;fontColor=#232F3E;gradientColor=none;fillColor=#8C4FFF;strokeColor=none;dashed=0;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=12;fontStyle=0;aspect=fixed;pointerEvents=1;shape=mxgraph.aws4.application_load_balancer;" 
          vertex="1" parent="public-subnet">
          <mxGeometry x="301" y="31" width="78" height="78" as="geometry"/>
        </mxCell>
        
        <!-- Private Subnet (VPC 내부) -->
        <mxCell id="private-subnet" value="Private Subnet" 
          style="sketch=0;outlineConnect=0;gradientColor=none;html=1;whiteSpace=wrap;fontSize=11;fontStyle=0;shape=mxgraph.aws4.group;grIcon=mxgraph.aws4.group_subnet;strokeColor=#147EBA;fillColor=#E6F2F8;verticalAlign=top;align=left;spacingLeft=30;fontColor=#147EBA;dashed=0;container=1;" 
          vertex="1" parent="vpc">
          <mxGeometry x="20" y="200" width="680" height="140" as="geometry"/>
        </mxCell>
        
        <!-- EC2 (Private Subnet 내부) -->
        <mxCell id="ec2" value="EC2&#xa;Instance" 
          style="sketch=0;outlineConnect=0;fontColor=#232F3E;gradientColor=none;fillColor=#ED7100;strokeColor=none;dashed=0;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=12;fontStyle=0;aspect=fixed;pointerEvents=1;shape=mxgraph.aws4.ec2_instance;" 
          vertex="1" parent="private-subnet">
          <mxGeometry x="301" y="31" width="78" height="78" as="geometry"/>
        </mxCell>
        
        <!-- Data Subnet (VPC 내부) -->
        <mxCell id="data-subnet" value="Data Subnet" 
          style="sketch=0;outlineConnect=0;gradientColor=none;html=1;whiteSpace=wrap;fontSize=11;fontStyle=0;shape=mxgraph.aws4.group;grIcon=mxgraph.aws4.group_subnet;strokeColor=#147EBA;fillColor=#E6F2F8;verticalAlign=top;align=left;spacingLeft=30;fontColor=#147EBA;dashed=0;container=1;" 
          vertex="1" parent="vpc">
          <mxGeometry x="20" y="360" width="680" height="140" as="geometry"/>
        </mxCell>
        
        <!-- RDS Primary -->
        <mxCell id="rds-primary" value="RDS&#xa;Primary" 
          style="sketch=0;outlineConnect=0;fontColor=#232F3E;gradientColor=none;fillColor=#C925D1;strokeColor=none;dashed=0;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=12;fontStyle=0;aspect=fixed;pointerEvents=1;shape=mxgraph.aws4.rds_instance;" 
          vertex="1" parent="data-subnet">
          <mxGeometry x="241" y="31" width="78" height="78" as="geometry"/>
        </mxCell>
        
        <!-- RDS Standby -->
        <mxCell id="rds-standby" value="RDS&#xa;Standby" 
          style="sketch=0;outlineConnect=0;fontColor=#232F3E;gradientColor=none;fillColor=#C925D1;strokeColor=none;dashed=0;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=12;fontStyle=0;aspect=fixed;pointerEvents=1;shape=mxgraph.aws4.rds_instance;" 
          vertex="1" parent="data-subnet">
          <mxGeometry x="361" y="31" width="78" height="78" as="geometry"/>
        </mxCell>
        
        <!-- Connections (정확한 연결점 지정) -->
        <mxCell id="edge1" value="HTTPS:443" 
          style="endArrow=classic;html=1;exitX=0.5;exitY=1;exitDx=0;exitDy=0;entryX=0.5;entryY=0;entryDx=0;entryDy=0;edgeStyle=orthogonalEdgeStyle;rounded=1;curved=0;" 
          edge="1" parent="1" source="alb" target="ec2">
          <mxGeometry relative="1" as="geometry"/>
        </mxCell>
        
        <mxCell id="edge2" value="TCP:3306" 
          style="endArrow=classic;html=1;exitX=0.5;exitY=1;exitDx=0;exitDy=0;entryX=0.5;entryY=0;entryDx=0;entryDy=0;edgeStyle=orthogonalEdgeStyle;rounded=1;curved=0;" 
          edge="1" parent="1" source="ec2" target="rds-primary">
          <mxGeometry relative="1" as="geometry"/>
        </mxCell>
        
        <!-- RDS Replication (점선) -->
        <mxCell id="edge3" value="Sync Replication" 
          style="endArrow=classic;startArrow=classic;html=1;exitX=1;exitY=0.5;exitDx=0;exitDy=0;entryX=0;entryY=0.5;entryDx=0;entryDy=0;edgeStyle=orthogonalEdgeStyle;rounded=1;curved=0;dashed=1;dashPattern=5 5;" 
          edge="1" parent="1" source="rds-primary" target="rds-standby">
          <mxGeometry relative="1" as="geometry"/>
        </mxCell>
      </root>
    </mxGraphModel>
  </diagram>
</mxfile>
```

**이 예시의 주요 특징:**
- VPC, Subnet에 `container=1` 속성 적용
- 자식 노드는 부모 기준 상대 좌표 사용
- AWS 공식 색상 코드 적용 (Public: #E9F3E6, Private: #E6F2F8)
- 연결선에 프로토콜/포트 라벨 추가
- RDS 복제는 점선(`dashed=1`)으로 표현
- 모든 연결점 명시 (`exitX`, `exitY`, `entryX`, `entryY`)

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

## 🎨 아키텍처 설계 및 배치 규칙

### 1. 계층 구조 및 좌표 체계 (Hierarchy)

- **Container 속성**: VPC, AZ, Subnet 등 그룹화 요소는 반드시 `container=1` 속성을 포함해야 함
- **상대 좌표**: 그룹 내 자식 노드의 `x, y` 좌표는 반드시 부모 노드의 좌측 상단(0,0)을 기준으로 한 상대 좌표로 계산할 것
- **Z-Order**: XML 생성 시 부모 노드를 자식 노드보다 먼저 기술하여 레이어 겹침 방지

### 2. 표준 스타일 적용 (Official AWS Colors)

- **VPC**: `fillColor=none;strokeColor=#248814;dashed=0;`
- **Public Subnet**: `fillColor=#E9F3E6;strokeColor=#248814;dashed=0;`
- **Private Subnet**: `fillColor=#E6F2F8;strokeColor=#147EBA;dashed=0;`
- **Security Group**: `fillColor=none;strokeColor=#DD3522;dashed=0;strokeWidth=2;`

### 3. 흐름 및 연결 규칙 (Traffic Flow)

- **방향성**: 외부 트래픽(User/Route53)은 좌측/상단에서 시작하여 우측/하단으로 흐르도록 배치
- **Edge 스타일**: 연결선은 `edgeStyle=orthogonalEdgeStyle;rounded=1;curved=0;` 기본 사용
- **라벨링**: 연결선(`mxCell`의 `value`)에 프로토콜/포트 명시 (예: "HTTPS:443", "TCP:3306")
- **동기화**: DB 복제 등 동기화 흐름은 `dashed=1;` 스타일의 점선으로 표기
- **연결점 명시**: `exitX`, `exitY`, `entryX`, `entryY` 속성으로 정확한 연결점 지정

### 4. 배치 간격 표준

- **화면 크기**: x=0-800, y=0-600 (단일 페이지 뷰포트)
- **외부 여백**: x=40, y=40부터 시작
- **아이콘 크기**: 기본 78x78px 유지
- **컴포넌트 간격**: 수평/수직 150-200px 간격 유지
- **그룹 내부 여백**: 박스 내 리소스는 최소 20px Padding 유지
- **각 요소 고유 ID**: 모든 mxCell은 고유한 ID 필수

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
