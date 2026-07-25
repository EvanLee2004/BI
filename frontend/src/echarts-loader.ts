/**
 * 2.6.3·D1：ECharts 异步加载器——看端首屏不静态 import echarts，
 * 图表进视口再拉 echarts chunk，首包 gz 可控。
 */
import type { EChartsType } from 'echarts/core'

export type EchartsNS = typeof import('echarts/core')

let _mod: EchartsNS | null = null
let _loading: Promise<EchartsNS> | null = null

export async function loadEcharts(): Promise<EchartsNS> {
  if (_mod) return _mod
  if (!_loading) {
    _loading = (async () => {
      const echarts = await import('echarts/core')
      const { BarChart, LineChart, PieChart, HeatmapChart } = await import('echarts/charts')
      const {
        GridComponent,
        TooltipComponent,
        LegendComponent,
        TitleComponent,
        VisualMapComponent,
        GraphicComponent,
        AxisPointerComponent,
        DatasetComponent,
        TransformComponent,
      } = await import('echarts/components')
      const { LabelLayout } = await import('echarts/features')
      const { CanvasRenderer, SVGRenderer } = await import('echarts/renderers')
      echarts.use([
        BarChart,
        LineChart,
        PieChart,
        HeatmapChart,
        GridComponent,
        TooltipComponent,
        LegendComponent,
        TitleComponent,
        VisualMapComponent,
        GraphicComponent,
        AxisPointerComponent,
        DatasetComponent,
        TransformComponent,
        LabelLayout,
        CanvasRenderer,
        SVGRenderer,
      ])
      _mod = echarts
      return echarts
    })()
  }
  return _loading
}

export type { EChartsType }
