import { DOCUMENT } from '@angular/common';
import { Component, ElementRef, Input, OnDestroy, ViewChild, computed, inject, signal } from '@angular/core';
import { UiLanguage } from '../chat/chat-api';

type WorkflowNodeType = 'trigger' | 'ai' | 'approval' | 'condition' | 'software' | 'script' | 'install' | 'batchInstall' | 'success' | 'blocked';
type PortId = 'next' | 'yes' | 'no';
interface NodeDefinition {
  type: WorkflowNodeType; categoryTh: string; categoryEn: string; labelTh: string; labelEn: string;
  descriptionTh: string; descriptionEn: string; icon: string;
  outputs: Array<{ id: PortId; labelTh: string; labelEn: string; top: number }>;
}
interface WorkflowNode { id: string; type: WorkflowNodeType; labelTh: string; labelEn: string; descriptionTh: string; descriptionEn: string; x: number; y: number; }
interface WorkflowEdge { id: string; fromNodeId: string; fromPort: PortId; toNodeId: string; }

const NODE_WIDTH = 224;
const NODE_HEIGHT = 144;
const WORLD_WIDTH = 1800;
const WORLD_HEIGHT = 900;
const NODE_DEFINITIONS: NodeDefinition[] = [
  { type: 'trigger', categoryTh: 'เริ่มต้น', categoryEn: 'Trigger', labelTh: 'เริ่ม Workflow', labelEn: 'Start workflow', descriptionTh: 'จุดเริ่มต้นของงาน', descriptionEn: 'Entry point for this workflow', icon: '▶', outputs: [{ id: 'next', labelTh: 'ถัดไป', labelEn: 'Next', top: 70 }] },
  { type: 'ai', categoryTh: 'AI', categoryEn: 'AI', labelTh: 'วิเคราะห์ด้วย AI', labelEn: 'AI analysis', descriptionTh: 'วิเคราะห์คำขอและสร้างผลลัพธ์ที่มีโครงสร้าง', descriptionEn: 'Analyze the request and produce structured output', icon: '✳', outputs: [{ id: 'next', labelTh: 'ถัดไป', labelEn: 'Next', top: 70 }] },
  { type: 'approval', categoryTh: 'อนุมัติ', categoryEn: 'Approval', labelTh: 'รอการอนุมัติ', labelEn: 'Request approval', descriptionTh: 'หยุดรอผู้ใช้ตรวจสอบและอนุมัติ', descriptionEn: 'Pause for explicit user review and approval', icon: '✓', outputs: [{ id: 'next', labelTh: 'อนุมัติแล้ว', labelEn: 'Approved', top: 70 }] },
  { type: 'condition', categoryTh: 'เงื่อนไข', categoryEn: 'Logic', labelTh: 'ตรวจสอบเงื่อนไข', labelEn: 'Check condition', descriptionTh: 'แยกเส้นทางตามผลตรวจสอบ', descriptionEn: 'Choose a path based on a condition', icon: '◇', outputs: [{ id: 'yes', labelTh: 'ผ่าน', labelEn: 'Yes', top: 52 }, { id: 'no', labelTh: 'ไม่ผ่าน', labelEn: 'No', top: 96 }] },
  { type: 'software', categoryTh: 'Software Hub', categoryEn: 'Software Hub', labelTh: 'ตรวจสอบซอฟต์แวร์', labelEn: 'Check software', descriptionTh: 'ค้นหาและตรวจสอบข้อมูลซอฟต์แวร์ (ตัวอย่าง)', descriptionEn: 'Discover and verify software metadata (sample)', icon: '▦', outputs: [{ id: 'next', labelTh: 'ตรวจสอบแล้ว', labelEn: 'Checked', top: 70 }] },
  { type: 'script', categoryTh: 'Execution', categoryEn: 'Execution', labelTh: 'รัน Custom Script', labelEn: 'Run custom script', descriptionTh: 'PowerShell, BAT/CMD, Python หรือ Node.js · ต้นแบบเท่านั้น ไม่รันจริง', descriptionEn: 'PowerShell, BAT/CMD, Python, or Node.js · prototype only, no execution', icon: '⌘', outputs: [{ id: 'next', labelTh: 'ทำงานต่อ', labelEn: 'Continue', top: 70 }] },
  { type: 'install', categoryTh: 'Software Hub', categoryEn: 'Software Hub', labelTh: 'ติดตั้งโปรแกรม', labelEn: 'Install software', descriptionTh: 'เลือก Package และตรวจสอบ Publisher / Version / Source · Dry Run เท่านั้น', descriptionEn: 'Select package and review publisher, version, and source · Dry Run only', icon: '↓', outputs: [{ id: 'next', labelTh: 'ตามแผน', labelEn: 'Planned', top: 70 }] },
  { type: 'batchInstall', categoryTh: 'Software Hub', categoryEn: 'Software Hub', labelTh: 'ติดตั้งหลายโปรแกรม', labelEn: 'Batch install', descriptionTh: 'จัดชุดรายการติดตั้งและกำหนดนโยบายเมื่อบางรายการล้มเหลว · ไม่ติดตั้งจริง', descriptionEn: 'Compose package batch and failure policy · no real installation', icon: '▤', outputs: [{ id: 'next', labelTh: 'จบชุดรายการ', labelEn: 'Batch complete', top: 70 }] },
  { type: 'success', categoryTh: 'สิ้นสุด', categoryEn: 'End', labelTh: 'จบงานสำเร็จ', labelEn: 'Finish successfully', descriptionTh: 'สิ้นสุดเส้นทางที่ผ่านเงื่อนไข', descriptionEn: 'End the successful path', icon: '●', outputs: [] },
  { type: 'blocked', categoryTh: 'สิ้นสุด', categoryEn: 'End', labelTh: 'จบงาน / ถูกระงับ', labelEn: 'Finish / blocked', descriptionTh: 'สิ้นสุดเส้นทางที่ไม่ผ่านเงื่อนไข', descriptionEn: 'End the path that did not pass the condition', icon: '■', outputs: [] },
];

@Component({ selector: 'app-workflow-builder', standalone: true, templateUrl: './workflow-builder.html' })
export class WorkflowBuilderComponent implements OnDestroy {
  private readonly document = inject(DOCUMENT);
  @Input() language: UiLanguage = 'th';
  @ViewChild('canvasWorld') private canvasWorld?: ElementRef<HTMLDivElement>;
  protected readonly definitions = NODE_DEFINITIONS;
  protected readonly zoom = signal(1);
  protected readonly fullScreen = signal(false);
  protected readonly showMainMenu = signal(false);
  protected readonly showNodeLibrary = signal(true);
  protected readonly showProperties = signal(true);
  protected readonly connectionSource = signal<{ nodeId: string; portId: PortId } | null>(null);
  protected readonly connectionPointer = signal<{ x: number; y: number } | null>(null);
  protected readonly selectedNodeId = signal<string | null>('node-4');
  protected readonly selectedEdgeId = signal<string | null>(null);
  protected readonly message = signal('');
  protected readonly nodes = signal<WorkflowNode[]>([
    { id: 'node-1', type: 'trigger', labelTh: 'รับคำขอ', labelEn: 'Request received', descriptionTh: 'เริ่มเมื่อได้รับคำขอจากผู้ใช้', descriptionEn: 'Starts when a user request is received', x: 70, y: 210 },
    { id: 'node-2', type: 'ai', labelTh: 'วิเคราะห์คำขอ', labelEn: 'Analyze request', descriptionTh: 'จัดประเภทและเตรียมข้อมูลสำหรับขั้นตอนถัดไป', descriptionEn: 'Classify the request and prepare structured input', x: 350, y: 210 },
    { id: 'node-3', type: 'approval', labelTh: 'ขออนุมัติจากผู้ใช้', labelEn: 'Request user approval', descriptionTh: 'แสดงรายละเอียดให้ผู้ใช้ตรวจสอบก่อนดำเนินการ', descriptionEn: 'Show the exact details for user review before proceeding', x: 630, y: 210 },
    { id: 'node-4', type: 'condition', labelTh: 'ผ่านการตรวจสอบหรือไม่?', labelEn: 'Did the review pass?', descriptionTh: 'แยกเส้นทางตามผลการตรวจสอบ', descriptionEn: 'Choose a path based on the review result', x: 910, y: 210 },
    { id: 'node-5', type: 'software', labelTh: 'ตรวจสอบ Software Hub', labelEn: 'Check Software Hub', descriptionTh: 'ค้นหาและตรวจสอบข้อมูลซอฟต์แวร์ในโหมดตัวอย่าง', descriptionEn: 'Discover and verify software metadata in this sample only', x: 1220, y: 70 },
    { id: 'node-6', type: 'success', labelTh: 'พร้อมสำหรับขั้นตอนถัดไป', labelEn: 'Ready for next step', descriptionTh: 'จบตัวอย่างเส้นทางที่ผ่านเงื่อนไข', descriptionEn: 'End the sample path that passed validation', x: 1520, y: 70 },
    { id: 'node-7', type: 'blocked', labelTh: 'หยุดและแจ้งผู้ใช้', labelEn: 'Stop and notify user', descriptionTh: 'จบเส้นทางเมื่อไม่ผ่านเงื่อนไข', descriptionEn: 'End the path when the condition is not met', x: 1220, y: 370 },
  ]);
  protected readonly edges = signal<WorkflowEdge[]>([
    { id: 'edge-1', fromNodeId: 'node-1', fromPort: 'next', toNodeId: 'node-2' },
    { id: 'edge-2', fromNodeId: 'node-2', fromPort: 'next', toNodeId: 'node-3' },
    { id: 'edge-3', fromNodeId: 'node-3', fromPort: 'next', toNodeId: 'node-4' },
    { id: 'edge-4', fromNodeId: 'node-4', fromPort: 'yes', toNodeId: 'node-5' },
    { id: 'edge-5', fromNodeId: 'node-4', fromPort: 'no', toNodeId: 'node-7' },
    { id: 'edge-6', fromNodeId: 'node-5', fromPort: 'next', toNodeId: 'node-6' },
  ]);
  protected readonly selectedNode = computed(() => this.nodes().find((node) => node.id === this.selectedNodeId()) ?? null);
  protected readonly selectedEdge = computed(() => this.edges().find((edge) => edge.id === this.selectedEdgeId()) ?? null);
  private nextNodeNumber = 8;
  private nextEdgeNumber = 7;
  private dragState: { nodeId: string; pointerId: number; offsetX: number; offsetY: number } | null = null;
  private connectionDragState: { nodeId: string; portId: PortId; pointerId: number; startX: number; startY: number; moved: boolean } | null = null;
  private suppressNextPortClick = false;

  protected isThai(): boolean { return this.language === 'th'; }
  protected toggleNodeLibrary(): void { this.showNodeLibrary.update((value) => !value); }
  protected toggleProperties(): void { this.showProperties.update((value) => !value); }
  protected toggleFullScreen(): void {
    const next = !this.fullScreen();
    this.fullScreen.set(next);
    this.document.documentElement.classList.toggle('workflow-fullscreen', next);
    if (!next) { this.showMainMenu.set(false); this.document.documentElement.classList.remove('workflow-nav-visible'); }
  }
  protected toggleMainMenu(): void {
    const next = !this.showMainMenu();
    this.showMainMenu.set(next);
    this.document.documentElement.classList.toggle('workflow-nav-visible', next);
  }
  protected exitFullScreen(): void {
    if (!this.fullScreen()) return;
    this.fullScreen.set(false);
    this.document.documentElement.classList.remove('workflow-fullscreen', 'workflow-nav-visible');
    this.showMainMenu.set(false);
  }
  ngOnDestroy(): void { this.document.documentElement.classList.remove('workflow-fullscreen', 'workflow-nav-visible'); }
  protected definition(type: WorkflowNodeType): NodeDefinition { return NODE_DEFINITIONS.find((item) => item.type === type) ?? NODE_DEFINITIONS[0]; }
  protected outputPorts(type: WorkflowNodeType): NodeDefinition['outputs'] { return this.definition(type).outputs; }
  protected categoryLabel(type: WorkflowNodeType): string { const item = this.definition(type); return this.isThai() ? item.categoryTh : item.categoryEn; }
  protected nodeDescription(type: WorkflowNodeType): string { const item = this.definition(type); return this.isThai() ? item.descriptionTh : item.descriptionEn; }
  protected nodeLabel(node: WorkflowNode): string { return this.isThai() ? node.labelTh : node.labelEn; }
  protected nodeDetail(node: WorkflowNode): string { return this.isThai() ? node.descriptionTh : node.descriptionEn; }
  protected edgeLabel(edge: WorkflowEdge): string {
    const definition = this.definition(this.nodes().find((node) => node.id === edge.fromNodeId)?.type ?? 'trigger');
    const port = definition.outputs.find((item) => item.id === edge.fromPort);
    return port ? (this.isThai() ? port.labelTh : port.labelEn) : '';
  }
  protected edgePath(edge: WorkflowEdge): string {
    const source = this.nodes().find((node) => node.id === edge.fromNodeId);
    const target = this.nodes().find((node) => node.id === edge.toNodeId);
    if (!source || !target) return '';
    const port = this.definition(source.type).outputs.find((item) => item.id === edge.fromPort);
    const x1 = source.x + NODE_WIDTH, y1 = source.y + (port?.top ?? 70) + 8;
    const x2 = target.x, y2 = target.y + 78, bend = Math.max(52, Math.abs(x2 - x1) * 0.42);
    return 'M ' + x1 + ' ' + y1 + ' C ' + (x1 + bend) + ' ' + y1 + ', ' + (x2 - bend) + ' ' + y2 + ', ' + x2 + ' ' + y2;
  }
  protected connectionPreviewPath(): string {
    const source = this.connectionSource(), point = this.connectionPointer();
    if (!source || !point) return '';
    const node = this.nodes().find((item) => item.id === source.nodeId);
    if (!node) return '';
    const port = this.definition(node.type).outputs.find((item) => item.id === source.portId);
    const x1 = node.x + NODE_WIDTH, y1 = node.y + (port?.top ?? 70) + 8;
    const bend = Math.max(45, Math.abs(point.x - x1) * 0.35);
    return 'M ' + x1 + ' ' + y1 + ' C ' + (x1 + bend) + ' ' + y1 + ', ' + (point.x - bend) + ' ' + point.y + ', ' + point.x + ' ' + point.y;
  }
  protected edgeLabelX(edge: WorkflowEdge): number {
    const source = this.nodes().find((node) => node.id === edge.fromNodeId), target = this.nodes().find((node) => node.id === edge.toNodeId);
    return source && target ? (source.x + NODE_WIDTH + target.x) / 2 : 0;
  }
  protected edgeLabelY(edge: WorkflowEdge): number {
    const source = this.nodes().find((node) => node.id === edge.fromNodeId), target = this.nodes().find((node) => node.id === edge.toNodeId);
    if (!source || !target) return 0;
    const port = this.definition(source.type).outputs.find((item) => item.id === edge.fromPort);
    return (source.y + (port?.top ?? 70) + 8 + target.y + 78) / 2 - 8;
  }
  protected addNode(type: WorkflowNodeType): void {
    const index = Math.max(0, this.nodes().length - 7);
    this.addNodeAt(type, 70 + (index % 4) * 270, 420 + Math.floor(index / 4) * 175);
  }
  private addNodeAt(type: WorkflowNodeType, x: number, y: number): void {
    const definition = this.definition(type);
    const node: WorkflowNode = {
      id: 'node-' + this.nextNodeNumber++, type, labelTh: definition.labelTh, labelEn: definition.labelEn, descriptionTh: definition.descriptionTh, descriptionEn: definition.descriptionEn,
      x: Math.max(20, Math.min(WORLD_WIDTH - NODE_WIDTH - 20, x)),
      y: Math.max(20, Math.min(WORLD_HEIGHT - NODE_HEIGHT - 20, y)),
    };
    this.nodes.update((items) => [...items, node]);
    this.selectNode(node.id);
    this.message.set(this.isThai() ? 'เพิ่ม Node แล้ว สามารถลากย้ายหรือเชื่อมพอร์ตได้' : 'Node added. Drag it or connect its ports.');
  }
  protected onPaletteDragStart(event: DragEvent, type: WorkflowNodeType): void {
    event.dataTransfer?.setData('application/x-workflow-node', type);
    if (event.dataTransfer) event.dataTransfer.effectAllowed = 'copy';
  }
  protected allowDrop(event: DragEvent): void { event.preventDefault(); if (event.dataTransfer) event.dataTransfer.dropEffect = 'copy'; }
  protected onDrop(event: DragEvent): void {
    event.preventDefault();
    const type = event.dataTransfer?.getData('application/x-workflow-node') ?? '';
    if (!this.isNodeType(type)) return;
    const rect = this.canvasWorld?.nativeElement.getBoundingClientRect();
    if (!rect) return;
    this.addNodeAt(type, (event.clientX - rect.left) / this.zoom() - NODE_WIDTH / 2, (event.clientY - rect.top) / this.zoom() - NODE_HEIGHT / 2);
  }
  private isNodeType(value: string): value is WorkflowNodeType { return NODE_DEFINITIONS.some((item) => item.type === value); }
  protected startNodeDrag(event: PointerEvent, node: WorkflowNode): void {
    if (event.button !== 0) return;
    event.preventDefault(); event.stopPropagation();
    const rect = this.canvasWorld?.nativeElement.getBoundingClientRect();
    if (!rect) return;
    const scale = this.zoom();
    this.dragState = { nodeId: node.id, pointerId: event.pointerId, offsetX: (event.clientX - rect.left) / scale - node.x, offsetY: (event.clientY - rect.top) / scale - node.y };
    (event.currentTarget as HTMLElement).setPointerCapture(event.pointerId);
    this.selectNode(node.id);
  }
  protected onCanvasPointerMove(event: PointerEvent): void {
    const world = this.canvasWorld?.nativeElement;
    const connection = this.connectionDragState;
    if (connection && world && connection.pointerId === event.pointerId) {
      if (!connection.moved && Math.hypot(event.clientX - connection.startX, event.clientY - connection.startY) > 5) {
        connection.moved = true;
        this.connectionSource.set({ nodeId: connection.nodeId, portId: connection.portId });
        this.selectNode(connection.nodeId);
        this.message.set(this.isThai() ? 'ลากเส้นไปวางบนพอร์ต Input ของ Node ปลายทาง' : 'Drop the connection on a target node input.');
      }
      if (connection.moved && world) {
        const rect = world.getBoundingClientRect(), scale = this.zoom();
        this.connectionPointer.set({ x: (event.clientX - rect.left) / scale, y: (event.clientY - rect.top) / scale });
      }
    }
    const drag = this.dragState;
    if (!drag || !world || drag.pointerId !== event.pointerId) return;
    const rect = world.getBoundingClientRect(), scale = this.zoom();
    const x = (event.clientX - rect.left) / scale - drag.offsetX, y = (event.clientY - rect.top) / scale - drag.offsetY;
    this.nodes.update((items) => items.map((node) => node.id === drag.nodeId
      ? { ...node, x: Math.max(0, Math.min(WORLD_WIDTH - NODE_WIDTH, x)), y: Math.max(0, Math.min(WORLD_HEIGHT - NODE_HEIGHT, y)) } : node));
  }
  protected endNodeDrag(event: PointerEvent): void {
    const connection = this.connectionDragState;
    if (connection?.pointerId === event.pointerId) {
      if (connection.moved && event.type === 'pointerup') {
        const eventTarget = event.target instanceof HTMLElement ? event.target : null;
        const target = eventTarget ?? this.document.elementFromPoint(event.clientX, event.clientY) as HTMLElement | null;
        const input = target?.closest('.node-port--input') as HTMLElement | null;
        const targetNodeId = input?.dataset['nodeId'];
        if (targetNodeId) this.completeConnection(targetNodeId);
        else {
          this.connectionSource.set(null);
          this.message.set(this.isThai() ? 'วางเส้นเชื่อมบนพอร์ต Input เพื่อเชื่อม Node' : 'Drop the connection on a node input port.');
        }
        this.suppressNextPortClick = true;
      }
      this.connectionDragState = null;
      this.connectionPointer.set(null);
    }
    if (this.dragState?.pointerId === event.pointerId) this.dragState = null;
  }
  protected onNodeKeydown(event: KeyboardEvent, node: WorkflowNode): void {
    if (event.target instanceof HTMLElement && event.target.closest('button, input, textarea, select')) return;
    const step = event.shiftKey ? 40 : 10;
    const offsets: Record<string, [number, number]> = { ArrowUp: [0, -step], ArrowDown: [0, step], ArrowLeft: [-step, 0], ArrowRight: [step, 0] };
    const offset = offsets[event.key];
    if (!offset) return;
    event.preventDefault();
    this.selectNode(node.id);
    this.nodes.update((items) => items.map((item) => item.id === node.id
      ? { ...item, x: Math.max(0, Math.min(WORLD_WIDTH - NODE_WIDTH, item.x + offset[0])), y: Math.max(0, Math.min(WORLD_HEIGHT - NODE_HEIGHT, item.y + offset[1])) }
      : item));
  }
  protected selectNode(nodeId: string): void { this.selectedNodeId.set(nodeId); this.selectedEdgeId.set(null); }
  protected selectCanvas(): void { this.selectedNodeId.set(null); this.selectedEdgeId.set(null); }
  protected selectEdge(event: Event, edge: WorkflowEdge): void { event.stopPropagation(); this.selectedEdgeId.set(edge.id); this.selectedNodeId.set(null); }
  protected startConnectionDrag(event: PointerEvent, nodeId: string, portId: PortId): void {
    if (event.button !== 0) return;
    event.stopPropagation();
    this.suppressNextPortClick = false;
    this.connectionDragState = { nodeId, portId, pointerId: event.pointerId, startX: event.clientX, startY: event.clientY, moved: false };
  }
  protected connectFrom(nodeId: string, portId: PortId, event: MouseEvent): void {
    event.stopPropagation();
    if (this.suppressNextPortClick) {
      this.suppressNextPortClick = false;
      if (event.detail > 0) return;
    }
    if (this.connectionSource()?.nodeId === nodeId && this.connectionSource()?.portId === portId) {
      this.connectionSource.set(null); this.connectionPointer.set(null);
      this.message.set(this.isThai() ? 'ยกเลิกการเชื่อมต่อ' : 'Connection cancelled.'); return;
    }
    this.connectionSource.set({ nodeId, portId }); this.selectNode(nodeId);
    this.message.set(this.isThai() ? 'ลากไปยังพอร์ต Input หรือคลิกพอร์ตด้านซ้ายของ Node ปลายทาง' : 'Drag to a target input, or click its input port.');
  }
  protected connectTo(nodeId: string, event: MouseEvent): void {
    event.stopPropagation();
    if (this.suppressNextPortClick) {
      this.suppressNextPortClick = false;
      if (event.detail > 0) return;
    }
    if (!this.connectionSource()) {
      this.selectNode(nodeId);
      this.message.set(this.isThai() ? 'เริ่มจากพอร์ต Output ด้านขวาของ Node ต้นทาง' : 'Start from an output port on a source node.');
      return;
    }
    this.completeConnection(nodeId);
  }
  private completeConnection(nodeId: string): void {
    const source = this.connectionSource();
    if (!source) return;
    if (source.nodeId === nodeId) { this.message.set(this.isThai() ? 'ไม่สามารถเชื่อม Node เข้าหาตัวเองได้' : 'A node cannot connect to itself.'); return; }
    if (this.edges().some((edge) => edge.fromNodeId === source.nodeId && edge.fromPort === source.portId && edge.toNodeId === nodeId)) { this.message.set(this.isThai() ? 'เส้นเชื่อมนี้มีอยู่แล้ว' : 'This connection already exists.'); return; }
    if (this.edges().some((edge) => edge.toNodeId === nodeId)) { this.message.set(this.isThai() ? 'พอร์ตปลายทางนี้มีเส้นเชื่อมแล้ว' : 'This input already has a connection.'); return; }
    if (this.wouldCreateCycle(source.nodeId, nodeId)) { this.message.set(this.isThai() ? 'ไม่อนุญาตให้สร้างวงจรย้อนกลับใน Prototype นี้' : 'Cycles are not supported in this prototype.'); return; }
    this.edges.update((items) => [...items, { id: 'edge-' + this.nextEdgeNumber++, fromNodeId: source.nodeId, fromPort: source.portId, toNodeId: nodeId }]);
    this.connectionSource.set(null); this.connectionPointer.set(null); this.selectNode(nodeId);
    this.message.set(this.isThai() ? 'เชื่อม Node สำเร็จ' : 'Nodes connected.');
  }
  private wouldCreateCycle(fromNodeId: string, toNodeId: string): boolean {
    const visited = new Set<string>(), stack = [toNodeId];
    while (stack.length) {
      const current = stack.pop();
      if (!current || visited.has(current)) continue;
      if (current === fromNodeId) return true;
      visited.add(current);
      for (const edge of this.edges()) if (edge.fromNodeId === current) stack.push(edge.toNodeId);
    }
    return false;
  }
  protected updateSelectedLabel(event: Event): void {
    const value = (event.target as HTMLInputElement).value.slice(0, 80), id = this.selectedNodeId();
    if (!id) return;
    this.nodes.update((items) => items.map((node) => node.id === id ? (this.isThai() ? { ...node, labelTh: value } : { ...node, labelEn: value }) : node));
  }
  protected updateSelectedDescription(event: Event): void {
    const value = (event.target as HTMLTextAreaElement).value.slice(0, 240), id = this.selectedNodeId();
    if (!id) return;
    this.nodes.update((items) => items.map((node) => node.id === id ? (this.isThai() ? { ...node, descriptionTh: value } : { ...node, descriptionEn: value }) : node));
  }
  protected removeSelectedNode(): void {
    const id = this.selectedNodeId();
    if (!id) return;
    this.nodes.update((items) => items.filter((node) => node.id !== id));
    this.edges.update((items) => items.filter((edge) => edge.fromNodeId !== id && edge.toNodeId !== id));
    this.selectedNodeId.set(null); this.connectionSource.set(null);
    this.message.set(this.isThai() ? 'ลบ Node และเส้นเชื่อมที่เกี่ยวข้องแล้ว' : 'Node and its connections removed.');
  }
  protected removeSelectedEdge(): void {
    const id = this.selectedEdgeId();
    if (!id) return;
    this.edges.update((items) => items.filter((edge) => edge.id !== id));
    this.selectedEdgeId.set(null); this.message.set(this.isThai() ? 'ลบเส้นเชื่อมแล้ว' : 'Connection removed.');
  }
  protected zoomIn(): void { this.zoom.update((value) => Math.min(1.3, Number((value + 0.1).toFixed(2)))); }
  protected zoomOut(): void { this.zoom.update((value) => Math.max(0.65, Number((value - 0.1).toFixed(2)))); }
  protected resetZoom(): void { this.zoom.set(1); }
  protected get zoomLabel(): string { return Math.round(this.zoom() * 100) + '%'; }
}
