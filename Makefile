.PHONY: reclaim-docker-cruft

# Read-only helper for docs/runbooks/reclaim-docker-cruft.md.
# Prints Docker disk usage and what is active/reclaimable. It does NOT prune —
# the destructive `docker builder/image prune` steps stay manual, run by hand
# on the production host after reviewing this output.
reclaim-docker-cruft:
	@echo "== docker disk usage =="
	@docker system df
	@echo "\n== images in use by running containers (must survive) =="
	@docker ps --format '{{.Image}}' | sort -u
	@echo "\n== all images (newest first) =="
	@docker images --format 'table {{.Repository}}\t{{.Tag}}\t{{.Size}}\t{{.CreatedSince}}'
	@echo "\nReview the above, then follow docs/runbooks/reclaim-docker-cruft.md."
	@echo "Prune commands are intentionally NOT run by this target."
