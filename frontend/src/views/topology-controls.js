export const TOPOLOGY_HELP = Object.freeze({
  load: '读取已有拓扑结果，不重新扫描设备',
  discoverAll: '扫描全部服务器并更新拓扑结果',
  discoverCurrent: '仅扫描右侧当前选中的服务器',
  reset: '恢复画布的缩放比例和位置',
})

export const TOPOLOGY_NOTICE = '拓扑发现方式：服务器通过每个 UP 状态的网口发送 ARP 探测，再到已关联的交换机查询是否学习到该接口的 MAC 地址。因此，发现的链路不能保证两端为物理直连。'

export function selectedServerFromNode(node) {
  return node?.type === 'server' ? node : null
}

export function discoveryServerIds(node) {
  const server = selectedServerFromNode(node)
  return server ? [server.entity_id] : null
}
