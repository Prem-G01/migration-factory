# Migration Runbook

## Pre-migration checklist

- [ ] Source infrastructure fully parsed and canonical model validated
- [ ] Translation report reviewed — all MANUAL/UNSUPPORTED resources have a plan
- [ ] Security scan completed — no CRITICAL findings unresolved
- [ ] Compliance evaluation completed — all required frameworks passing
- [ ] FinOps analysis reviewed — cost projections approved by finance
- [ ] Rollback plan generated, reviewed, and approved by operations
- [ ] Migration waves defined and sequenced
- [ ] Cutover window approved by stakeholders
- [ ] On-call team briefed and escalation path documented
- [ ] DNS TTLs lowered 24-48 hours before cutover
- [ ] Data synchronization mechanisms tested (DMS, Storage Transfer, rsync)
- [ ] Target cloud project/account provisioned with appropriate IAM
- [ ] Terraform state backend configured on target cloud
- [ ] Monitoring and alerting configured on target infrastructure

## Phase 1: Networking

### Objective
Establish the network foundation on the target cloud.

### Steps
1. Review generated `main.tf` for network resources (VPC, subnets, firewall rules, NAT, routes)
2. Run `terraform init` in the output directory
3. Run `terraform plan` — review every resource to be created
4. Run `terraform apply` after approval
5. Validate: ping tests between subnets, verify NAT egress, confirm firewall rules

### Validation checkpoint
- [ ] VPC created and routing tables correct
- [ ] All subnets created in correct regions/zones
- [ ] Firewall rules match security requirements
- [ ] NAT gateway operational (test egress from private subnet)
- [ ] VPN/peering established if required

### Rollback trigger
Any networking resource fails to create or connectivity tests fail.

## Phase 2: IAM and Security

### Steps
1. Apply IAM resources (service accounts, custom roles, IAM bindings)
2. Apply secrets (Secret Manager entries — values migrated out-of-band)
3. Apply certificates

### Validation checkpoint
- [ ] Service accounts created with correct permissions
- [ ] Secrets accessible from target compute resources
- [ ] No overly permissive IAM bindings (verify with Security Engine)

## Phase 3: Storage

### Steps
1. Create target storage buckets/disks/file systems
2. Initiate data synchronization (Storage Transfer Service, gsutil rsync)
3. Verify data integrity with checksums

### Validation checkpoint
- [ ] All buckets created with correct policies
- [ ] Data sync initiated and progressing
- [ ] Encryption at rest verified

## Phase 4: Database

### Steps
1. Create Cloud SQL / Memorystore instances
2. Establish Private Service Access if required
3. Initiate database migration (DMS or dump/restore)
4. Verify schema and row counts

### Validation checkpoint
- [ ] Database instances healthy
- [ ] Connectivity from compute subnet verified
- [ ] Data integrity verified (row counts, checksum)
- [ ] Replication lag acceptable (if using continuous sync)

## Phase 5: Compute and Load Balancing

### Steps
1. Deploy compute instances / GKE clusters / Cloud Run services
2. Configure load balancers
3. Deploy application code
4. Run smoke tests

### Validation checkpoint
- [ ] All instances running and passing health checks
- [ ] Load balancer routing traffic correctly
- [ ] Application responding on expected endpoints

## Cutover procedure

1. **Freeze** — stop all deployments on source cloud
2. **Final sync** — run final data synchronization for all stateful resources
3. **Verify consistency** — compare checksums between source and target
4. **DNS switch** — update DNS records to point to target infrastructure
5. **Validate** — confirm traffic flowing through target, error rates normal
6. **Monitor** — watch dashboards for 30 minutes minimum
7. **Declare success** or initiate rollback

## Post-migration verification

- [ ] All health checks green for 1+ hours
- [ ] Error rates at or below baseline
- [ ] Database query performance within acceptable range
- [ ] All monitoring alerts active and tested
- [ ] Log aggregation capturing from all target resources
- [ ] Cost tracking active in target cloud billing
- [ ] Source infrastructure placed in read-only standby (keep for rollback window)

## Rollback procedure

See `ROLLBACK_GUIDE.md` for the detailed procedure. Key points:

1. Revert DNS to source infrastructure
2. Verify source is still operational
3. Stop data sync to prevent overwriting source with stale target data
4. Run `terraform destroy` on target in reverse dependency order
5. Document the failure and lessons learned
