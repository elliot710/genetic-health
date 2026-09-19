/**
 * @vitest-environment jsdom
 *
 * "Acute lymphoid leukemia 28%" was the owner's complaint, and it was a fair
 * one: the 28 was a composite confidence that a variant is damaging, printed
 * beside a disease name where it reads as the chance of having the disease.
 * The headline must carry the qualitative band; the number belongs in the
 * expanded view, next to the classification it supports.
 */
import { describe, it, expect, afterEach } from 'vitest'
import { render, screen, cleanup } from '@testing-library/react'

import { EvidenceBand, PathogenicityScoreDetail } from '../shared'

const theme = { textSecondary: 'text-slate-400' } as Parameters<typeof PathogenicityScoreDetail>[0]['theme']

afterEach(cleanup)

describe('EvidenceBand', () => {
  it('states a likely-benign classification in words', () => {
    render(<EvidenceBand classification="likely_benign" />)
    expect(screen.getByText('Likely benign')).toBeDefined()
  })

  it('prints no percentage beside the condition name', () => {
    const { container } = render(<EvidenceBand classification="likely_benign" />)
    expect(container.textContent).not.toContain('%')
  })

  it('reports an unscored variant as unclear, not benign', () => {
    render(<EvidenceBand classification={null} />)
    expect(screen.getByText('Evidence unclear')).toBeDefined()
  })

  it('does not colour an unclear classification as reassuring', () => {
    const { container } = render(<EvidenceBand classification={null} />)
    expect(container.firstElementChild?.className).not.toMatch(/green/)
  })

  it('still distinguishes a pathogenic classification', () => {
    render(<EvidenceBand classification="pathogenic" />)
    expect(screen.getByText('Pathogenic')).toBeDefined()
  })
})

describe('PathogenicityScoreDetail', () => {
  it('labels the number so it cannot be read as a disease probability', () => {
    render(<PathogenicityScoreDetail classification="likely_benign" score={28} theme={theme} />)
    expect(screen.getByText('Variant pathogenicity score:')).toBeDefined()
  })

  it('shows the score on an explicit scale rather than as a bare percentage', () => {
    const { container } = render(
      <PathogenicityScoreDetail classification="likely_benign" score={28} theme={theme} />
    )
    expect(container.textContent).toContain('28 / 100')
  })

  it('keeps the classification adjacent to the number', () => {
    const { container } = render(
      <PathogenicityScoreDetail classification="likely_benign" score={28} theme={theme} />
    )
    expect(container.textContent).toContain('likely benign')
  })

  it('renders nothing when the variant was never scored', () => {
    const { container } = render(
      <PathogenicityScoreDetail classification="uncertain" score={null} theme={theme} />
    )
    expect(container.firstChild).toBeNull()
  })
})
