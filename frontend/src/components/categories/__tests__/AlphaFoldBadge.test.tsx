/**
 * @vitest-environment jsdom
 *
 * The badge read "AF 57%" next to a disease name. "AF" is allele frequency to
 * anyone reading a genetics report, so a protein-model confidence score was
 * legible as "57% of the population carries this". The label must not be
 * ambiguous, and its colour must not editorialise about the finding.
 */
import { describe, it, expect, afterEach } from 'vitest'
import { render, screen, cleanup } from '@testing-library/react'

import { AlphaFoldBadge, formatPopulationFrequency } from '../shared'

afterEach(cleanup)

describe('AlphaFoldBadge', () => {
  it('names AlphaFold explicitly', () => {
    render(<AlphaFoldBadge confidence={57} />)
    expect(screen.getByText(/AlphaFold/)).toBeDefined()
  })

  it('never renders the bare token AF', () => {
    const { container } = render(<AlphaFoldBadge confidence={57} />)
    expect(container.textContent).not.toMatch(/\bAF\b/)
  })

  it('states the confidence tier in words, not only in colour', () => {
    const { container } = render(<AlphaFoldBadge confidence={57} />)
    expect(container.textContent).toContain('moderate confidence')
  })

  it('does not colour high model confidence as reassuring', () => {
    const { container } = render(<AlphaFoldBadge confidence={92} />)
    expect(container.firstElementChild?.className).not.toMatch(/green/)
  })

  it('renders nothing without a confidence value', () => {
    const { container } = render(<AlphaFoldBadge confidence={null} />)
    expect(container.firstChild).toBeNull()
  })

  it('keeps the residue breakdown in the tooltip', () => {
    render(<AlphaFoldBadge confidence={57} highPct={0.42} lowPct={0.11} />)
    expect(screen.getByTitle(/42% very high confidence residues/)).toBeDefined()
  })
})

describe('formatPopulationFrequency', () => {
  it('keeps a rare allele visible instead of rounding it to zero', () => {
    expect(formatPopulationFrequency(0.000012)).toBe('0.0012%')
  })

  it('renders a common allele with one decimal', () => {
    expect(formatPopulationFrequency(0.34)).toBe('34.0%')
  })

  it('reports an absent frequency as unknown rather than as zero', () => {
    expect(formatPopulationFrequency(0)).toBe('unknown')
  })
})
