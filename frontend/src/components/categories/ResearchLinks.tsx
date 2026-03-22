'use client'

import React from 'react'
import { ExternalLink } from 'lucide-react'

interface ResearchLinksProps {
  rsid?: string
  gene?: string
  isDarkMode?: boolean
  compact?: boolean
}

const DB_LINKS = {
  dbSNP: (rsid: string) => `https://www.ncbi.nlm.nih.gov/snp/${rsid}`,
  ClinVar: (rsid: string) => `https://www.ncbi.nlm.nih.gov/clinvar/?term=${rsid}`,
  SNPedia: (rsid: string) => `https://www.snpedia.com/index.php/${rsid}`,
  Ensembl: (rsid: string) => `https://www.ensembl.org/Homo_sapiens/Variation/Explore?v=${rsid}`,
  PubMed: (rsid: string) => `https://pubmed.ncbi.nlm.nih.gov/?term=${rsid}`,
}

const GENE_LINKS = {
  GeneCards: (gene: string) => `https://www.genecards.org/cgi-bin/carddisp.pl?gene=${gene}`,
  OMIM: (gene: string) => `https://omim.org/search?search=${gene}`,
  UniProt: (gene: string) => `https://www.uniprot.org/uniprotkb?query=${gene}+AND+organism_id:9606`,
}

const LINK_COLORS: Record<string, string> = {
  dbSNP: 'text-blue-400 hover:text-blue-300',
  ClinVar: 'text-orange-400 hover:text-orange-300',
  SNPedia: 'text-green-400 hover:text-green-300',
  Ensembl: 'text-purple-400 hover:text-purple-300',
  PubMed: 'text-yellow-400 hover:text-yellow-300',
  GeneCards: 'text-cyan-400 hover:text-cyan-300',
  OMIM: 'text-pink-400 hover:text-pink-300',
  UniProt: 'text-teal-400 hover:text-teal-300',
}

export default function ResearchLinks({ rsid, gene, isDarkMode = false, compact = false }: ResearchLinksProps) {
  if (!rsid && !gene) return null

  const variantLinks = rsid
    ? Object.entries(DB_LINKS).map(([name, fn]) => ({ name, url: fn(rsid) }))
    : []

  const geneLinks = gene && gene !== 'Unknown' && gene !== 'Multiple'
    ? Object.entries(GENE_LINKS).map(([name, fn]) => ({ name, url: fn(gene) }))
    : []

  const allLinks = [...variantLinks, ...geneLinks]

  if (allLinks.length === 0) return null

  if (compact) {
    return (
      <div className="flex flex-wrap gap-2">
        {allLinks.map(({ name, url }) => (
          <a
            key={name}
            href={url}
            target="_blank"
            rel="noopener noreferrer"
            className={`inline-flex items-center gap-1 text-xs font-medium ${LINK_COLORS[name] || 'text-blue-400 hover:text-blue-300'} transition-colors`}
          >
            {name}
            <ExternalLink className="h-3 w-3" />
          </a>
        ))}
      </div>
    )
  }

  return (
    <div className="space-y-2">
      <p className={`text-xs font-semibold ${isDarkMode ? 'text-white/50' : 'text-gray-500'} uppercase tracking-wider`}>
        Research & Databases
      </p>
      <div className="flex flex-wrap gap-x-4 gap-y-1.5">
        {allLinks.map(({ name, url }) => (
          <a
            key={name}
            href={url}
            target="_blank"
            rel="noopener noreferrer"
            className={`inline-flex items-center gap-1.5 text-sm font-medium ${LINK_COLORS[name] || 'text-blue-400 hover:text-blue-300'} transition-colors`}
          >
            {name}
            <ExternalLink className="h-3.5 w-3.5" />
          </a>
        ))}
      </div>
    </div>
  )
}

export { DB_LINKS, GENE_LINKS, LINK_COLORS }
