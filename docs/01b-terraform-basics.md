# Chapter 1b: Terraform fundamentals (side step)

Hands-on: [playground/terraform-basics/](../playground/terraform-basics/README.md)

## The language: HCL
`.tf` files are written in **HCL** (HashiCorp Configuration Language). It's a configuration
language, not a programming language: you describe **what should exist**.

It has only three building blocks:
```hcl
block_type "label1" "label2" {   # BLOCK: a type + 0–2 labels + { body }
  argument = value               # ARGUMENT: name = value
  nested_block {                 # blocks inside blocks
    other = 42
  }
}
```

Values: `"string"`, `2`, `true`, `[80, 443]` (list), `{ env = "dev" }` (map).
String interpolation: `"kind-${var.cluster_name}"`.

## The block types you'll meet

| Block | Meaning | Analogy |
|-------|---------|---------|
| `terraform { required_providers {...} }` | which plugins to download | imports / dependencies |
| `provider "aws" {...}` | configure a plugin (region, credentials...) | creating an API client |
| `variable "x" {...}` | an input, read with `var.x` | function parameter |
| `resource "TYPE" "NAME" {...}` | **a thing that should exist and that Terraform owns** | the actual work |
| `output "x" {...}` | a value printed after apply | return value |
| `data "TYPE" "NAME" {...}` | *reads* something existing, doesn't own it | a lookup |
| `locals {...}` | named intermediate values, read with `local.x` | local variables |

In `resource "local_file" "greeting"`, the **TYPE** (`local_file`) comes from the provider:
its prefix `local_` = the `local` provider, just like `kind_cluster` comes from `kind` and
`aws_instance` from `aws`. The **NAME** (`greeting`) is your own nickname.

## References create the order
`TYPE.NAME.ATTRIBUTE` (e.g. `local_file.greeting.filename`, `kind_cluster.this.endpoint`).
If B references A, Terraform creates A first. You never write the steps; Terraform builds
a dependency graph from the references.

## Three surprising facts
1. **File names don't matter.** All `.tf` files in a folder are merged. `main.tf`/`variables.tf`/`outputs.tf` is only a convention.
2. **Order in the file doesn't matter.** References decide the order.
3. **Declarative.** You write "this should exist". A second `apply` does nothing if reality already matches.

## The loop and the state
```
 .tf files          terraform.tfstate          real world
 (what you WANT)    (what Terraform BUILT)     (files / Docker / AWS)
        └──────── terraform plan: refresh, compare, print a diff ───────┘
              + create    ~ update in place    - destroy    -/+ replace
        terraform apply: perform the diff, then update the state
```
- **State** is Terraform's memory of "this resource in my code = that real object". Never edit it by hand, and never commit it (it can contain secrets).
- Terraform is **not a running process**. It only checks and fixes drift when you run it. Kubernetes, in contrast, reconciles continuously.

## Commands
| Command | Does |
|---------|------|
| `terraform init` | download providers (once per folder, or after adding one) |
| `terraform fmt` | auto-format your files |
| `terraform validate` | check the syntax |
| `terraform plan` | show the diff, change nothing |
| `terraform apply` | perform the diff (asks for confirmation) |
| `terraform destroy` | delete everything in the state |
| `terraform output` | print the outputs |
| `terraform state list` / `state show X` | inspect the memory |
