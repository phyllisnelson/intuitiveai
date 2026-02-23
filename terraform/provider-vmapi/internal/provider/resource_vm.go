package provider

import (
	"context"
	"errors"
	"fmt"

	"github.com/hashicorp/terraform-plugin-framework/diag"
	"github.com/hashicorp/terraform-plugin-framework/path"
	"github.com/hashicorp/terraform-plugin-framework/resource"
	"github.com/hashicorp/terraform-plugin-framework/resource/schema"
	"github.com/hashicorp/terraform-plugin-framework/resource/schema/planmodifier"
	"github.com/hashicorp/terraform-plugin-framework/resource/schema/listplanmodifier"
	"github.com/hashicorp/terraform-plugin-framework/resource/schema/mapplanmodifier"
	"github.com/hashicorp/terraform-plugin-framework/resource/schema/stringplanmodifier"
	"github.com/hashicorp/terraform-plugin-framework/types"
)

var _ resource.Resource = &vmResource{}
var _ resource.ResourceWithConfigure = &vmResource{}

type vmResource struct {
	client *APIClient
}

type vmResourceModel struct {
	ID             types.String `tfsdk:"id"`
	Name           types.String `tfsdk:"name"`
	FlavorID       types.String `tfsdk:"flavor_id"`
	ImageID        types.String `tfsdk:"image_id"`
	NetworkID      types.String `tfsdk:"network_id"`
	KeyName        types.String `tfsdk:"key_name"`
	SecurityGroups types.List   `tfsdk:"security_groups"`
	UserData       types.String `tfsdk:"user_data"`
	Metadata       types.Map    `tfsdk:"metadata"`
	Status         types.String `tfsdk:"status"`
	CreatedAt      types.String `tfsdk:"created_at"`
	UpdatedAt      types.String `tfsdk:"updated_at"`
}

func NewVMResource() resource.Resource {
	return &vmResource{}
}

func (r *vmResource) Metadata(_ context.Context, req resource.MetadataRequest, resp *resource.MetadataResponse) {
	resp.TypeName = req.ProviderTypeName + "_vm"
}

func (r *vmResource) Schema(_ context.Context, _ resource.SchemaRequest, resp *resource.SchemaResponse) {
	resp.Schema = schema.Schema{
		Attributes: map[string]schema.Attribute{
			"id": schema.StringAttribute{
				Computed: true,
			},
			"name": schema.StringAttribute{
				Required: true,
				PlanModifiers: []planmodifier.String{
					stringplanmodifier.RequiresReplace(),
				},
			},
			"flavor_id": schema.StringAttribute{
				Required: true,
			},
			"image_id": schema.StringAttribute{
				Required: true,
				PlanModifiers: []planmodifier.String{
					stringplanmodifier.RequiresReplace(),
				},
			},
			"network_id": schema.StringAttribute{
				Optional: true,
				PlanModifiers: []planmodifier.String{
					stringplanmodifier.RequiresReplace(),
				},
			},
			"key_name": schema.StringAttribute{
				Optional: true,
				PlanModifiers: []planmodifier.String{
					stringplanmodifier.RequiresReplace(),
				},
			},
			"security_groups": schema.ListAttribute{
				Optional:    true,
				Computed:    true,
				ElementType: types.StringType,
				PlanModifiers: []planmodifier.List{
					listplanmodifier.RequiresReplace(),
				},
			},
			"user_data": schema.StringAttribute{
				Optional:  true,
				Sensitive: true,
				PlanModifiers: []planmodifier.String{
					stringplanmodifier.RequiresReplace(),
				},
			},
			"metadata": schema.MapAttribute{
				Optional:    true,
				Computed:    true,
				ElementType: types.StringType,
				PlanModifiers: []planmodifier.Map{
					mapplanmodifier.RequiresReplace(),
				},
			},
			"status": schema.StringAttribute{
				Computed: true,
			},
			"created_at": schema.StringAttribute{
				Computed: true,
			},
			"updated_at": schema.StringAttribute{
				Computed: true,
			},
		},
	}
}

func (r *vmResource) Configure(_ context.Context, req resource.ConfigureRequest, resp *resource.ConfigureResponse) {
	if req.ProviderData == nil {
		return
	}

	client, ok := req.ProviderData.(*APIClient)
	if !ok {
		resp.Diagnostics.AddError(
			"Unexpected Provider Data Type",
			fmt.Sprintf("Expected *APIClient, got: %T", req.ProviderData),
		)
		return
	}

	r.client = client
}

func (r *vmResource) Create(ctx context.Context, req resource.CreateRequest, resp *resource.CreateResponse) {
	if r.client == nil {
		resp.Diagnostics.AddError("Unconfigured Provider", "The provider is not configured.")
		return
	}

	var plan vmResourceModel
	resp.Diagnostics.Append(req.Plan.Get(ctx, &plan)...)
	if resp.Diagnostics.HasError() {
		return
	}

	createReq, diags := expandVMCreateRequest(ctx, plan)
	resp.Diagnostics.Append(diags...)
	if resp.Diagnostics.HasError() {
		return
	}

	vmID, taskID, err := r.client.CreateVM(ctx, createReq)
	if err != nil {
		resp.Diagnostics.AddError("Create VM Failed", err.Error())
		return
	}

	if err := r.client.WaitTask(ctx, taskID); err != nil {
		resp.Diagnostics.AddError("VM Provisioning Failed", err.Error())
		return
	}

	vm, err := r.client.GetVM(ctx, vmID)
	if err != nil {
		resp.Diagnostics.AddError("Read VM After Create Failed", err.Error())
		return
	}

	state, diags := flattenVMState(ctx, plan, vm)
	resp.Diagnostics.Append(diags...)
	if resp.Diagnostics.HasError() {
		return
	}

	resp.Diagnostics.Append(resp.State.Set(ctx, &state)...)
}

func (r *vmResource) Read(ctx context.Context, req resource.ReadRequest, resp *resource.ReadResponse) {
	if r.client == nil {
		resp.Diagnostics.AddError("Unconfigured Provider", "The provider is not configured.")
		return
	}

	var state vmResourceModel
	resp.Diagnostics.Append(req.State.Get(ctx, &state)...)
	if resp.Diagnostics.HasError() {
		return
	}

	vm, err := r.client.GetVM(ctx, state.ID.ValueString())
	if err != nil {
		if errors.Is(err, ErrNotFound) {
			resp.State.RemoveResource(ctx)
			return
		}
		resp.Diagnostics.AddError("Read VM Failed", err.Error())
		return
	}

	newState, diags := flattenVMState(ctx, state, vm)
	resp.Diagnostics.Append(diags...)
	if resp.Diagnostics.HasError() {
		return
	}

	resp.Diagnostics.Append(resp.State.Set(ctx, &newState)...)
}

func (r *vmResource) Update(ctx context.Context, req resource.UpdateRequest, resp *resource.UpdateResponse) {
	if r.client == nil {
		resp.Diagnostics.AddError("Unconfigured Provider", "The provider is not configured.")
		return
	}

	var plan vmResourceModel
	var state vmResourceModel

	resp.Diagnostics.Append(req.Plan.Get(ctx, &plan)...)
	resp.Diagnostics.Append(req.State.Get(ctx, &state)...)
	if resp.Diagnostics.HasError() {
		return
	}

	if plan.FlavorID.ValueString() != state.FlavorID.ValueString() {
		taskID, err := r.client.ResizeVM(ctx, state.ID.ValueString(), plan.FlavorID.ValueString())
		if err != nil {
			resp.Diagnostics.AddError("Resize VM Failed", err.Error())
			return
		}
		if err := r.client.WaitTask(ctx, taskID); err != nil {
			resp.Diagnostics.AddError("Resize VM Task Failed", err.Error())
			return
		}
	}

	vm, err := r.client.GetVM(ctx, state.ID.ValueString())
	if err != nil {
		if errors.Is(err, ErrNotFound) {
			resp.State.RemoveResource(ctx)
			return
		}
		resp.Diagnostics.AddError("Read VM After Update Failed", err.Error())
		return
	}

	newState, diags := flattenVMState(ctx, plan, vm)
	resp.Diagnostics.Append(diags...)
	if resp.Diagnostics.HasError() {
		return
	}

	resp.Diagnostics.Append(resp.State.Set(ctx, &newState)...)
}

func (r *vmResource) Delete(ctx context.Context, req resource.DeleteRequest, resp *resource.DeleteResponse) {
	if r.client == nil {
		resp.Diagnostics.AddError("Unconfigured Provider", "The provider is not configured.")
		return
	}

	var state vmResourceModel
	resp.Diagnostics.Append(req.State.Get(ctx, &state)...)
	if resp.Diagnostics.HasError() {
		return
	}

	taskID, err := r.client.DeleteVM(ctx, state.ID.ValueString())
	if err != nil {
		if errors.Is(err, ErrNotFound) {
			return
		}
		resp.Diagnostics.AddError("Delete VM Failed", err.Error())
		return
	}

	if err := r.client.WaitTask(ctx, taskID); err != nil {
		resp.Diagnostics.AddError("Delete VM Task Failed", err.Error())
		return
	}
}

func (r *vmResource) ImportState(ctx context.Context, req resource.ImportStateRequest, resp *resource.ImportStateResponse) {
	resource.ImportStatePassthroughID(ctx, path.Root("id"), req, resp)
}

func expandVMCreateRequest(ctx context.Context, plan vmResourceModel) (vmCreateRequest, diag.Diagnostics) {
	var diags diag.Diagnostics

	req := vmCreateRequest{
		Name:     plan.Name.ValueString(),
		FlavorID: plan.FlavorID.ValueString(),
		ImageID:  plan.ImageID.ValueString(),
	}

	if !plan.NetworkID.IsNull() && !plan.NetworkID.IsUnknown() {
		v := plan.NetworkID.ValueString()
		req.NetworkID = &v
	}
	if !plan.KeyName.IsNull() && !plan.KeyName.IsUnknown() {
		v := plan.KeyName.ValueString()
		req.KeyName = &v
	}
	if !plan.UserData.IsNull() && !plan.UserData.IsUnknown() {
		v := plan.UserData.ValueString()
		req.UserData = &v
	}

	if !plan.SecurityGroups.IsNull() && !plan.SecurityGroups.IsUnknown() {
		var groups []string
		d := plan.SecurityGroups.ElementsAs(ctx, &groups, false)
		diags.Append(d...)
		req.SecurityGroups = groups
	}

	if !plan.Metadata.IsNull() && !plan.Metadata.IsUnknown() {
		var metadata map[string]string
		d := plan.Metadata.ElementsAs(ctx, &metadata, false)
		diags.Append(d...)
		req.Metadata = metadata
	}

	return req, diags
}

func flattenVMState(ctx context.Context, base vmResourceModel, vm vmResponse) (vmResourceModel, diag.Diagnostics) {
	var diags diag.Diagnostics
	state := base

	state.ID = types.StringValue(vm.ID)
	state.Name = types.StringValue(vm.Name)
	state.FlavorID = types.StringValue(vm.FlavorID)
	state.ImageID = types.StringValue(vm.ImageID)
	if vm.KeyName == "" {
		state.KeyName = types.StringNull()
	} else {
		state.KeyName = types.StringValue(vm.KeyName)
	}
	state.Status = types.StringValue(vm.Status)
	state.CreatedAt = types.StringValue(vm.CreatedAt)

	if vm.UpdatedAt == "" {
		state.UpdatedAt = types.StringNull()
	} else {
		state.UpdatedAt = types.StringValue(vm.UpdatedAt)
	}

	sg, d := types.ListValueFrom(ctx, types.StringType, vm.SecurityGroups)
	diags.Append(d...)
	state.SecurityGroups = sg

	md, d := types.MapValueFrom(ctx, types.StringType, vm.Metadata)
	diags.Append(d...)
	state.Metadata = md

	return state, diags
}
