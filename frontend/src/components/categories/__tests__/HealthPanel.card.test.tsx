/**
 * @vitest-environment jsdom
 *
 * Panel-level checks on the card the owner complained about. The EvidenceBand
 * unit tests cover the badge in isolation; this renders the real HealthPanel
 * with payloads shaped like the live one and asserts what a reader sees.
 *
 * The live card read "Acute lymphoid leukemia 28% · Moderate Risk · GNB1
 * rs3820011" while its own detail said "Pathogenicity Score (likely benign)".
 * The same condition was named a second time, outside the card, under
 * "Key Recommendations → Moderate Risk Management → Watch: ...".
 */
import { describe, it, expect, afterEach } from 'vitest'
import { render, screen, cleanup } from '@testing-library/react'

import HealthPanel from '../HealthPanel'

const CONDITION = 'Acute lymphoid leukemia'

function payload(overrides: Record<string, unknown>) {
  return {
    health_risks: [{
      condition: CONDITION,
      risk_level: 'moderate',
      risk_score: '0.5',
      associated_variants: ['rs3820011'],
      recommendations: ['Consult with healthcare provider'],
      gene: 'GNB1',
      review_status: 'criteria provided, single submitter',
      ...overrides,
    }],
    pathogenicity_map: { rs3820011: { score: 28, classification: 'likely_benign' } },
    genotype_map: { rs3820011: 'AC' },
  }
}

const renderPanel = (data: unknown) =>
  render(<HealthPanel isDarkMode data={data as never} token="t" />)

afterEach(cleanup)

describe('a likely-benign finding', () => {
  const data = payload({ pathogenicity_classification: 'likely_benign', provenance: 'gene' })

  it('is filtered out of the card list by default', () => {
    renderPanel(data)
    expect(screen.getByText(/Health Risks \(0 of 1\)/)).toBeDefined()
  })

  it('is no longer named under Key Recommendations either', () => {
    const { container } = renderPanel(data)
    expect(container.textContent).not.toContain(`Watch: ${CONDITION}`)
  })

  it('raises no Moderate Risk Management heading', () => {
    const { container } = renderPanel(data)
    expect(container.textContent).not.toContain('Moderate Risk Management')
  })
})

describe('a finding the reader can actually see', () => {
  const data = payload({ pathogenicity_classification: 'uncertain', provenance: 'variant' })

  it('names the condition', () => {
    renderPanel(data)
    expect(screen.getByText(CONDITION)).toBeDefined()
  })

  it('prints no percentage next to the condition name', () => {
    renderPanel(data)
    const heading = screen.getByText(CONDITION)
    expect(heading.parentElement?.textContent).not.toMatch(/\d+%/)
  })

  it('states the evidence qualitatively instead', () => {
    const { container } = renderPanel(data)
    expect(container.textContent).toContain('Uncertain significance')
  })
})

describe('a gene-level association that passes the filter', () => {
  const data = payload({ pathogenicity_classification: 'uncertain', provenance: 'gene' })

  it('is labelled as an association, not as assessed risk', () => {
    const { container } = renderPanel(data)
    expect(container.textContent).toContain('Gene association')
  })

  it('is not offered as something for the reader to watch', () => {
    const { container } = renderPanel(data)
    expect(container.textContent).not.toContain(`Watch: ${CONDITION}`)
  })
})
